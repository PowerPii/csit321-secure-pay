"""URS 4.4.3 Availability: NFR-AVA-02 to NFR-AVA-04 at the URS's own numbers.

NFR-AVA-01 (kill the gateway container 5 times under traffic) needs the running stack; see
docs/test-report/MANUAL-TESTS.md.
"""
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from nfr_helpers import new_payment, submit

from apps.payments import reconciliation
from apps.payments.models import Operation, Payment
from apps.risk.models import ScreeningEvent

pytestmark = pytest.mark.django_db(databases=["default", "vault"])

def _luhn_card(n: int) -> str:
    """A distinct Luhn-valid test number, so the per-card burst rule does not block it."""
    body = f"4000123{n:08d}"
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return body + str((10 - total % 10) % 10)


def test_nfr_ava_02_150_requests_in_a_minute_from_one_key(shop, other_shop, settings):
    assert settings.GATEWAY_RULES["API_RATE_LIMIT_PER_MINUTE"] == 100
    url = "/v1/payments/pay_" + "A" * 24
    statuses = []
    for n in range(150):
        r = shop.get(url)
        statuses.append(r.status_code)
        if n >= 100:
            assert r.status_code == 429 and int(r["Retry-After"]) >= 1
            assert r.json()["error"]["code"] == "rate_limited"
        if n % 25 == 0:  # other keys are served normally throughout
            assert other_shop.get(url).status_code == 404
    assert statuses[:100] == [404] * 100 and statuses[100:] == [429] * 50


def _authorise_calls(fake_sim, payment):
    return [b for m, p, b in fake_sim.requests
            if p == "/sim/authorise" and b["payment_id"] == payment.public_id]


def _settle(op, deadline_seconds=3600):
    """Run the scheduled checks for one operation; return seconds until it ended."""
    elapsed = (op.next_check_at - op.created_at).total_seconds()
    for _ in range(20):
        Operation.objects.filter(pk=op.pk).update(
            next_check_at=timezone.now() - timedelta(seconds=1))
        before = timezone.now()
        reconciliation.reconcile_due()
        op.refresh_from_db()
        if op.status != "unresolved" or op.escalated_at:
            return elapsed
        elapsed += (op.next_check_at - before).total_seconds()
        assert elapsed <= deadline_seconds
    raise AssertionError("never settled or escalated")


def test_nfr_ava_03_twenty_unanswered_payments_end_or_escalate_within_an_hour(
        shop, fake_sim):
    cards = [_luhn_card(n) for n in range(20)]
    fake_sim.HANG = frozenset(cards)  # no reply to any of them (processing timeout)
    payments = []
    for n, number in enumerate(cards):
        payment = new_payment(shop)
        submit(payment, number)
        if n % 2 == 0:  # lost request: the simulator never recorded it
            fake_sim.records = {k: v for k, v in fake_sim.records.items()
                                if v.get("payment_id") != payment.public_id}
        payment.refresh_from_db()
        assert payment.status == "unresolved"
        payments.append(payment)

    # The first ten: the simulator answers status queries, so each reaches a final status.
    for payment in payments[:10]:
        op = Operation.objects.get(payment=payment)
        assert _settle(op) <= 3600
        payment.refresh_from_db()
        assert payment.status in ("authorised", "declined")
    # The other ten: status queries fail too, so each is escalated to an administrator.
    fake_sim.status_mode = "fail"
    for payment in payments[10:]:
        op = Operation.objects.get(payment=payment)
        assert _settle(op) <= 3600
        assert op.escalated_at is not None
        payment.refresh_from_db()
        assert payment.status == "unresolved"  # nobody guesses an outcome
    for payment in payments:  # none was submitted twice
        assert len(_authorise_calls(fake_sim, payment)) == 1


@pytest.mark.parametrize("mode", ["error", "slow"])
def test_nfr_ava_04_fifty_payments_blocked_while_screening_is_down(
        shop, fake_sim, settings, mode):
    """Screening stopped ("error"), and separately slower than 500 ms ("slow")."""
    settings.DEBUG = True  # the outage switch works only in DEBUG
    settings.RISK_SIMULATE_OUTAGE = mode
    assert settings.GATEWAY_RULES["SCREENING_TIMEOUT_MS"] == 500
    for _ in range(50):
        cache.clear()  # 50 different shoppers: the per-browser rate limit is not the subject
        payment = new_payment(shop)
        data = submit(payment).json()
        assert (data["status"], data["result"]) == ("blocked", "unavailable")
        api = shop.get(f"/v1/payments/{payment.public_id}").json()
        assert api["screening"] == {"decision": "not_screened"}
        assert api["outcome"]["reason"] == "screening_unavailable"
    assert fake_sim.requests == []  # none reached the processing simulator
    assert Payment.objects.filter(status="blocked").count() == 50
    events = ScreeningEvent.objects.all()
    assert events.count() == 50
    assert {(e.outcome, tuple(e.reasons)) for e in events} == {
        ("not_screened", ("screening_unavailable",))}
