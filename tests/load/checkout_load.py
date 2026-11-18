"""Checkout load test for NFR-PER-01 (docs/test-report/MANUAL-TESTS.md, M-PER-01).

    python3 tests/load/checkout_load.py --gateway https://gateway.<domain> \\
        --key-file deploy/secrets/securepay_api_key --rate 20 --seconds 300 --out per-01.json

Starts one payment every 1/rate seconds on a fixed schedule. Each payment is created with the
merchant API, then goes through the two calls the hosted checkout page makes: card entry and
submit. Those two are the "checkout responses" timed here. Cards are fresh numbers from the
simulator's demo approve range (4242 4200 ...), which the simulator approves at once, so its
delay is close to zero and the figure is an upper bound on the gateway's own time.

Pass: 95% of checkout responses within 2 s, the rate held (no attempt started more than
250 ms late), no 429 (raise the limits first, see M-PER-01), under 1% errors, and under 1% of
payments ending other than "authorised" (an HTTP 200 that blocks the payment, for example
screening_unavailable under overload, is not a success). Exit status 1 on a FAIL.
Needs only httpx (pip install httpx).
"""
import argparse
import json
import random
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

MAX_START_LAG_MS = 250


def demo_card(rng: random.Random) -> str:
    """A Luhn-valid number in the simulator's demo approve range 42424200xxxxxxxx."""
    body = "42424200" + "".join(str(rng.randrange(10)) for _ in range(7))
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return body + str((10 - total % 10) % 10)


def pct(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q / 100 * (len(ordered) - 1)))]


def one_payment(client, gateway, key, card, n, forwarded_for=None):
    out = {"n": n, "card_ms": None, "submit_ms": None, "statuses": [], "result": None,
           "error": None}
    # The checkout calls come from the customer's browser; with --spread-ips each payment
    # has its own client address, as real customers do (see --spread-ips).
    browser = {"X-Forwarded-For": forwarded_for} if forwarded_for else {}
    try:
        r = client.post(f"{gateway}/v1/payments", headers={
            "Authorization": f"Bearer {key}", "Idempotency-Key": str(uuid.uuid4())},
            json={"amount": 1990 + n % 50, "currency": "SGD",
                  "order_reference": f"LOAD-{n:06d}",
                  "return_url": "https://shop.example/orders/load/return",
                  "customer_email": f"load.{n}@example.com"})
        out["statuses"].append(r.status_code)
        if r.status_code != 201:
            out["error"] = f"create {r.status_code}"
            return out
        session = r.json()["checkout_url"].rstrip("/").rsplit("/", 1)[1]
        base = f"{gateway}/checkout/{session}"
        started = time.perf_counter()
        r = client.post(f"{base}/card", headers=browser, json={
            "number": card, "expiry_month": 12, "expiry_year": 2030, "cvc": "123",
            "privacy_consent": True})
        out["card_ms"] = (time.perf_counter() - started) * 1000
        out["statuses"].append(r.status_code)
        if r.status_code != 200:
            out["error"] = f"card {r.status_code}"
            return out
        started = time.perf_counter()
        r = client.post(f"{base}/submit", headers=browser, json={})
        out["submit_ms"] = (time.perf_counter() - started) * 1000
        out["statuses"].append(r.status_code)
        if r.status_code == 200:
            data = r.json()
            out["result"] = data.get("status")
            if out["result"] != "authorised":
                out["reason"] = data.get("result")  # e.g. "unavailable" = screening timed out
        else:
            out["error"] = f"submit {r.status_code}"
    except httpx.HTTPError as exc:
        out["error"] = type(exc).__name__
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--gateway", required=True, help="https://gateway.<domain>")
    parser.add_argument("--key-file", required=True, help="file holding the shop's API key")
    parser.add_argument("--rate", type=float, default=20.0, help="payments per second")
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--workers", type=int, default=0, help="threads (default 4 x rate)")
    parser.add_argument("--ca-bundle", default=None, help="extra CA file (local stack)")
    parser.add_argument("--out", default=None, help="write all timings as JSON here")
    parser.add_argument(
        "--spread-ips", action="store_true",
        help="give each payment its own browser address (X-Forwarded-For from 198.18.0.0/15). "
             "Only works against a gateway reached directly with TRUSTED_PROXY_HOPS=1 (a local "
             "run); through Caddy every payment comes from this machine's one address, so "
             "fraud screening counts all of them as one customer's attempts, which real "
             "traffic never does and which slows screening as the run goes on.")
    args = parser.parse_args(argv)

    gateway = args.gateway.rstrip("/")
    key = Path(args.key_file).read_text().strip()
    total = int(args.rate * args.seconds)
    workers = args.workers or max(8, int(args.rate * 4))
    rng = random.Random()
    cards = [demo_card(rng) for _ in range(total)]
    local = threading.local()
    lags, results = [], []

    def client():
        if not hasattr(local, "client"):
            local.client = httpx.Client(timeout=30, verify=args.ca_bundle or True)
        return local.client

    t0 = time.perf_counter()

    def run(n):
        due = t0 + n / args.rate
        delay = due - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        lags.append((time.perf_counter() - due) * 1000)
        ip = f"198.{18 + n // 65536 % 2}.{n // 256 % 256}.{n % 256}" if args.spread_ips else None
        results.append(one_payment(client(), gateway, key, cards[n], n, ip))

    print(f"{total} payments at {args.rate}/s for {args.seconds} s, {workers} threads ...",
          flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run, range(total)))
    wall = time.perf_counter() - t0

    times = [r[k] for r in results for k in ("card_ms", "submit_ms") if r[k] is not None]
    statuses = [s for r in results for s in r["statuses"]]
    errors = [r for r in results if r["error"]]
    outcomes = {}
    for r in results:
        outcomes[r["result"] or "error"] = outcomes.get(r["result"] or "error", 0) + 1
    not_authorised = total - outcomes.get("authorised", 0)
    reasons = {}
    for r in results:
        if r.get("reason"):
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    p95 = pct(times, 95)
    within = sum(1 for t in times if t <= 2000) / len(times) if times else 0
    summary = {
        "gateway": gateway, "spread_ips": args.spread_ips, "rate": args.rate, "seconds": args.seconds, "payments": total,
        "wall_seconds": round(wall, 1),
        "checkout_responses": len(times),
        "p50_ms": round(statistics.median(times), 1) if times else None,
        "p95_ms": round(p95, 1) if p95 is not None else None,
        "max_ms": round(max(times), 1) if times else None,
        "share_within_2s": round(within, 4),
        "max_start_lag_ms": round(max(lags), 1) if lags else None,
        "http_429": statuses.count(429),
        "errors": len(errors),
        "outcomes": outcomes,
        "not_authorised": not_authorised,
        "reasons": reasons,
    }
    passed = (p95 is not None and p95 <= 2000 and summary["http_429"] == 0
              and summary["max_start_lag_ms"] <= MAX_START_LAG_MS
              and len(errors) < 0.01 * total and not_authorised < 0.01 * total)
    summary["result"] = "PASS" if passed else "FAIL"
    print(json.dumps(summary, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "payments": results},
                                             indent=1))
    print(summary["result"])
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
