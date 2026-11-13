"""Measure screening time end to end (NFR-PER-02: p95 <= 200 ms over 1,000 payments).

    python manage.py benchmark_screening [--payments 1000] [--history 5000]

Inside one transaction that is rolled back at the end (nothing is left behind), it first
writes `--history` earlier screening events spread over the last 30 days, so the
prior-activity counts have rows to scan, then screens `--payments` new payments exactly as
checkout does (savepoint, statement timeout, feature queries, lists, rules, model, policy,
decision record) and reports the timings. Cards, emails and IPs come from small pools so
many attempts share history, as repeat customers and fraud bursts do. Run it on the demo
VM (`docker compose exec gateway python manage.py benchmark_screening`) for report figures.
"""
import random
import statistics
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.merchants.models import Merchant
from apps.payments.models import Payment
from apps.risk import hashing
from apps.risk.models import ScreeningEvent
from apps.risk.screening import screen_payment


class Rollback(Exception):
    pass


def pct(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


class Command(BaseCommand):
    help = "Benchmark fraud screening latency against the 200 ms p95 target."

    def add_arguments(self, parser):
        parser.add_argument("--payments", type=int, default=1000)
        parser.add_argument("--history", type=int, default=5000)
        parser.add_argument("--seed", type=int, default=321)

    def handle(self, *args, payments, history, seed, **options):
        # Synthetic benchmark data only, never used for security.
        rng = random.Random(seed)  # nosec B311
        cards = [f"{i:064x}" for i in range(max(50, payments // 4))]
        emails = [f"customer{i}@example.com" for i in range(max(50, payments // 3))]
        ips = [f"198.51.100.{i % 250 + 1}" for i in range(max(20, payments // 10))]
        timings, outcomes = [], {}
        try:
            with transaction.atomic():
                merchant = Merchant(name="Benchmark (rolled back)", status=Merchant.Status.ACTIVE)
                merchant.rotate_signing_secret()
                merchant.save()
                self._history(merchant, history, rng, cards, emails, ips)
                for _ in range(payments):
                    payment = Payment.create_for_merchant(
                        merchant, order_reference="BENCH", amount=rng.randint(500, 80_000),
                        return_url="https://shop.localhost/r",
                        customer_email=rng.choice(emails), card_fingerprint=rng.choice(cards))
                    started = time.perf_counter()
                    result = screen_payment(payment, ip=rng.choice(ips))
                    timings.append((time.perf_counter() - started) * 1000)
                    outcomes[result.outcome.value] = outcomes.get(result.outcome.value, 0) + 1
                raise Rollback
        except Rollback:
            pass

        target = settings.GATEWAY_RULES["SCREENING_TARGET_P95_MS"]
        budget = settings.GATEWAY_RULES["SCREENING_TIMEOUT_MS"]
        p95 = pct(timings, 95)
        self.stdout.write(
            f"{len(timings)} screenings over {history} earlier events\n"
            f"  mean {statistics.mean(timings):.1f} ms   p50 {pct(timings, 50):.1f} ms   "
            f"p95 {p95:.1f} ms   p99 {pct(timings, 99):.1f} ms   max {max(timings):.1f} ms\n"
            f"  over the {budget} ms budget: {sum(t > budget for t in timings)}\n"
            f"  outcomes: {dict(sorted(outcomes.items()))}\n"
            f"  NFR-PER-02 p95 <= {target} ms: {'PASS' if p95 <= target else 'FAIL'}")

    def _history(self, merchant, count, rng, cards, emails, ips):
        now = timezone.now()
        payments = [Payment.create_for_merchant(
            merchant, order_reference="BENCH-H", amount=1000,
            return_url="https://shop.localhost/r") for _ in range(count)]
        ScreeningEvent.objects.bulk_create([
            ScreeningEvent(
                public_id=f"scr_bench{i:019d}", payment=p, merchant=merchant,
                occurred_at=now - timedelta(seconds=rng.randint(1, 30 * 86400)), amount=1000,
                card_fingerprint=rng.choice(cards),
                email_hash=hashing.email_hash(rng.choice(emails)),
                ip_hash=hashing.ip_hash(rng.choice(ips)),
                outcome=rng.choice(["allow"] * 8 + ["verify", "block"]))
            for i, p in enumerate(payments)], batch_size=1000)
