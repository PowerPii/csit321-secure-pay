"""Screen payments at a steady rate from several threads and check the 200 ms p95 target.

    python manage.py loadtest_screening [--rate 20] [--seconds 60] [--workers 8] [--history 5000]

MVP sprint 7 latency check (NFR-PER-02 at 20 requests per second). Unlike
benchmark_screening, which screens one payment after another inside a rolled-back
transaction, this one commits, so concurrent attempts compete for the database the way real
checkouts do: each attempt runs in its own transaction on its own connection, with the
payment row locked, exactly as checkout calls screen_payment. Attempts are started on a fixed
schedule (attempt i at i / rate seconds); if the threads fall behind, the start lag is
reported and the run counts as failed, because the rate was not reached.

Everything is written under a temporary "Load test" merchant and deleted at the end. Uses the
installed model (RISK_MODEL_VERSION), so run it on the stack:

    docker compose -f deploy/compose.yaml exec gateway python manage.py loadtest_screening
"""
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.merchants.models import Merchant
from apps.payments.models import Payment
from apps.risk import hashing
from apps.risk.management.commands.benchmark_screening import pct
from apps.risk.models import ScreeningEvent
from apps.risk.scoring import active_model
from apps.risk.screening import screen_payment

MAX_START_LAG_MS = 100  # an attempt that starts later than this means the rate was not held


class Command(BaseCommand):
    help = "Screen payments at --rate per second for --seconds and report p95 latency."

    def add_arguments(self, parser):
        parser.add_argument("--rate", type=float, default=20.0)
        parser.add_argument("--seconds", type=float, default=60.0)
        parser.add_argument("--workers", type=int, default=8)
        parser.add_argument("--history", type=int, default=5000)
        parser.add_argument("--seed", type=int, default=321)

    def handle(self, *args, rate, seconds, workers, history, seed, **options):
        # Synthetic load-test data only, never used for security.
        rng = random.Random(seed)  # nosec B311
        total = max(1, round(rate * seconds))
        cards = [f"{i:064x}" for i in range(max(50, total // 4))]
        emails = [f"customer{i}@example.com" for i in range(max(50, total // 3))]
        ips = [f"198.51.100.{i % 250 + 1}" for i in range(max(20, total // 10))]
        plan = [(i / rate, rng.randint(500, 80_000), rng.choice(cards), rng.choice(emails),
                 rng.choice(ips)) for i in range(total)]
        model = active_model()

        merchant = Merchant(name="Load test (deleted after the run)",
                            status=Merchant.Status.ACTIVE)
        merchant.rotate_signing_secret()
        merchant.save()
        lock = threading.Lock()
        results = []  # (wall ms, pipeline ms, start lag ms, outcome)
        try:
            self._history(merchant, history, rng, cards, emails, ips)
            start = time.perf_counter() + 0.5

            def run(item):
                due, amount, card, email, ip = item
                try:
                    delay = start + due - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                    lag = (time.perf_counter() - start - due) * 1000
                    payment = Payment.create_for_merchant(
                        merchant, order_reference="LOAD", amount=amount,
                        return_url="https://shop.localhost/r", customer_email=email,
                        card_fingerprint=card)
                    began = time.perf_counter()
                    with transaction.atomic():
                        locked = Payment.objects.select_for_update().get(pk=payment.pk)
                        result = screen_payment(locked, ip=ip)
                    wall = (time.perf_counter() - began) * 1000
                    with lock:
                        results.append((wall, result.event.elapsed_ms, lag,
                                        result.outcome.value))
                finally:
                    connection.close()  # one connection per worker call, closed afterwards

            run_started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(run, plan))
            took = time.perf_counter() - run_started - 0.5
        finally:
            ScreeningEvent.objects.filter(merchant=merchant).delete()
            Payment.objects.filter(merchant=merchant).delete()
            merchant.delete()

        walls = [r[0] for r in results]
        pipeline = [r[1] for r in results]
        lags = [r[2] for r in results]
        outcomes = {}
        for r in results:
            outcomes[r[3]] = outcomes.get(r[3], 0) + 1
        target = settings.GATEWAY_RULES["SCREENING_TARGET_P95_MS"]
        budget = settings.GATEWAY_RULES["SCREENING_TIMEOUT_MS"]
        p95 = pct(walls, 95)
        rate_held = pct(lags, 95) <= MAX_START_LAG_MS
        unavailable = outcomes.get("not_screened", 0)
        passed = p95 <= target and rate_held and not unavailable
        self.stdout.write(
            f"model {model.version}: {len(results)} screenings at {rate:g}/s over {took:.1f} s "
            f"({len(results) / took:.1f}/s achieved), {workers} workers, "
            f"{history} earlier events\n"
            f"  screening (as checkout calls it): mean {statistics.mean(walls):.1f} ms   "
            f"p50 {pct(walls, 50):.1f}   p95 {p95:.1f}   p99 {pct(walls, 99):.1f}   "
            f"max {max(walls):.1f} ms\n"
            f"  pipeline only (decision record): p50 {pct(pipeline, 50):.1f}   "
            f"p95 {pct(pipeline, 95):.1f} ms\n"
            f"  start lag p95 {pct(lags, 95):.1f} ms (rate held: {'yes' if rate_held else 'no'})"
            f"   over the {budget} ms budget: {sum(w > budget for w in walls)}\n"
            f"  outcomes: {dict(sorted(outcomes.items()))}\n"
            f"  NFR-PER-02 p95 <= {target} ms at {rate:g}/s: {'PASS' if passed else 'FAIL'}")
        if not passed:  # a missed target fails the command (exit status 1)
            raise CommandError("NFR-PER-02 target missed")

    def _history(self, merchant, count, rng, cards, emails, ips):
        now = timezone.now()
        payments = [Payment.create_for_merchant(
            merchant, order_reference="LOAD-H", amount=1000,
            return_url="https://shop.localhost/r") for _ in range(count)]
        ScreeningEvent.objects.bulk_create([
            ScreeningEvent(
                payment=p, merchant=merchant, public_id=f"scr_load{i:020d}",
                occurred_at=now - timedelta(seconds=rng.randint(1, 30 * 86400)),
                amount=rng.randint(500, 80_000), card_fingerprint=rng.choice(cards),
                email_hash=hashing.email_hash(rng.choice(emails)),
                ip_hash=hashing.ip_hash(rng.choice(ips)),
                outcome=rng.choice(["allow"] * 8 + ["verify", "block"]))
            for i, p in enumerate(payments)], batch_size=1000)
