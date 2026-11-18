"""Real demo traffic for the Fraud insights charts: `bash deploy/demo.sh traffic`.

    python tests/integration/demo_traffic.py [--scale 1] [--minutes 0]

Every payment goes through the real gateway exactly like the shop's checkout: created with
the shop's API key, card vaulted and submitted on the hosted checkout, screened by the rules,
lists, model and policy, then sent to the simulated bank. Nothing is written to the database
directly, so the dashboard shows only what really happened (the demo-day rule: no synthetic
history in an audited gateway). One run, at --scale 1, makes about 55 payments:

    32  ordinary purchases with fresh demo cards        mostly allowed
     4  declined by the bank (insufficient funds)      allowed by screening, declined
     4  over S$ 500                                     step-up (high_amount rule)
     3  review@example.com                              step-up (review list)
     3  the blocked-list card 4000 0000 0000 0101      blocked (block list)
     2  blocked@example.com                             blocked (block list)
     7  one card tried 7 times quickly (card testing)  first 5 allowed, then blocked (burst)

Step-up payments are left waiting for their code. --minutes spreads the run over that many
minutes (for example 90, in the background), so the "Last 24 hours" chart shows several hours
of traffic; run it on a few days before the demo to fill "Last 7 days". The payments are real
test orders and stay on the dashboard; they are not in the shop's order list.
"""
import argparse
import os
import random
import ssl
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conftest import (  # noqa: E402
    BLOCKLISTED,
    GATEWAY_URL,
    MERCHANT_URL,
    _secret,
    session_id,
)

APPROVE_PREFIXES = ("42424200", "55555500")  # simulator demo ranges (SIMULATOR-CONTRACT.md 5)
DECLINE_PREFIX = "40000099"
MIN_GAP = 2.5  # seconds between payments


def luhn_ok(number: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(number)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def demo_card(rng: random.Random, prefix: str) -> str:
    body = prefix + "".join(str(rng.randrange(10)) for _ in range(15 - len(prefix)))
    return next(body + c for c in "0123456789" if luhn_ok(body + c))


def plan(rng: random.Random, scale: int, stamp: str) -> list[tuple[str, int, str, str]]:
    """(kind, amount in cents, card, email) in a shuffled but repeatable order."""
    email = lambda tag: f"{tag}.{stamp}.{uuid.uuid4().hex[:6]}@example.com"  # noqa: E731
    items = []
    for _ in range(scale):
        items += [("ordinary", rng.choice([1290, 2490, 3990, 5900, 8900, 12900, 19900, 34900]),
                   demo_card(rng, rng.choice(APPROVE_PREFIXES)), email("shopper"))
                  for _ in range(32)]
        items += [("declined", rng.randint(3000, 30000), demo_card(rng, DECLINE_PREFIX),
                   email("shopper")) for _ in range(4)]
        items += [("high amount", rng.choice([52900, 89900, 129900, 179900]),
                   demo_card(rng, APPROVE_PREFIXES[0]), email("bigspender")) for _ in range(4)]
        items += [("review list", rng.randint(2000, 20000), demo_card(rng, APPROVE_PREFIXES[1]),
                   "review@example.com") for _ in range(3)]
        items += [("blocked card", rng.randint(2000, 40000), BLOCKLISTED, email("shopper"))
                  for _ in range(3)]
        items += [("blocked email", rng.randint(2000, 40000), demo_card(rng, APPROVE_PREFIXES[0]),
                   "blocked@example.com") for _ in range(2)]
    rng.shuffle(items)
    # Card testing stays together: one card, small amounts, seconds apart.
    tester = demo_card(rng, APPROVE_PREFIXES[0])
    burst = [("card testing", rng.choice([100, 150, 200, 250]), tester, email("tester"))
             for _ in range(7)]
    at = rng.randrange(len(items) + 1)
    return items[:at] + burst + items[at:]


def client(base_url: str, **kwargs) -> httpx.Client:
    ca = os.environ.get("CADDY_ROOT_CA")
    verify = ssl.create_default_context(cafile=ca) if ca else True
    return httpx.Client(base_url=base_url, verify=verify, trust_env=False, timeout=30, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scale", type=int, default=1, help="Repeat the mix this many times.")
    parser.add_argument("--minutes", type=float, default=0, help="Spread the run over this long.")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    rng = random.Random(args.seed)  # nosec B311 - demo traffic, not security
    stamp = time.strftime("%d%H%M")
    items = plan(rng, max(1, min(args.scale, 10)), stamp)
    # The hosted checkout allows 60 calls a minute per IP address and each payment makes two,
    # so never go faster than one payment every 2.5 s.
    gap = max(MIN_GAP, args.minutes * 60 / max(1, len(items) - 1))
    api = client(GATEWAY_URL, headers={"Authorization": f"Bearer {_secret('securepay_api_key')}"})
    results: dict[str, dict[str, int]] = {}
    print(f"Running {len(items)} real payments through {GATEWAY_URL}"
          + f" over about {gap * len(items) / 60:.0f} minutes")
    for n, (kind, amount, card, email) in enumerate(items, 1):
        status = "error"
        try:
            created = api.post("/v1/payments", json={
                "amount": amount, "currency": "SGD", "order_reference": f"DEMO-{uuid.uuid4().hex[:8]}",
                "return_url": f"{MERCHANT_URL}/orders/demo/return", "customer_email": email},
                headers={"Idempotency-Key": str(uuid.uuid4())})
            created.raise_for_status()
            with client(GATEWAY_URL) as browser:
                base = f"/checkout/{session_id(created.json())}"
                browser.post(f"{base}/card", json={
                    "number": card, "expiry_month": 12, "expiry_year": 2030, "cvc": "123",
                    "privacy_consent": True}).raise_for_status()
                browser.post(f"{base}/submit", json={}).raise_for_status()
            status = api.get(f"/v1/payments/{created.json()['id']}").json()["status"]
        except httpx.HTTPError as exc:
            print(f"  {n:3d} {kind:13s} failed: {exc}")
        results.setdefault(kind, {}).setdefault(status, 0)
        results[kind][status] += 1
        time.sleep(MIN_GAP if kind == "card testing" else gap)
    api.close()
    print("\nKind           Payment status after screening and the bank")
    for kind, counts in sorted(results.items()):
        print(f"  {kind:13s} " + ", ".join(f"{s} {c}" for s, c in sorted(counts.items())))
    print("\nOpen the dashboard as the analyst: Fraud insights, Last 24 hours.")
    return 1 if any("error" in c for c in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
