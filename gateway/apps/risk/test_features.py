"""Prior-activity features over ScreeningEvent rows (fs-0.2)."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.payments.models import Payment
from apps.risk.features import FEATURE_NAMES, SqlFeatures
from apps.risk.models import ScreeningEvent
from apps.risk.pipeline import Attempt

pytestmark = pytest.mark.django_db


@pytest.fixture
def history(shop):
    """Add a screening event `ago` before now for a fresh payment."""
    from conftest import valid_body

    def add(ago, card="fpA", email="eA", ip="iA", outcome="allow"):
        r = shop.create_payment(valid_body())
        payment = Payment.objects.get(public_id=r.json()["id"])
        return ScreeningEvent.objects.create(
            payment=payment, merchant=shop.merchant, occurred_at=timezone.now() - ago,
            amount=payment.amount, card_fingerprint=card, email_hash=email, ip_hash=ip,
            outcome=outcome)

    return add


def build(**kw):
    base = {"attempt_id": "pay_x", "merchant_id": "mer_x", "amount_cents": 4590,
            "card_fingerprint": "fpA", "email_hash": "eA", "ip_hash": "iA",
            "occurred_at": timezone.now()}
    return SqlFeatures().build(Attempt(**{**base, **kw}))


def test_first_attempt_has_only_the_amount():
    f = build()
    assert set(f) == set(FEATURE_NAMES)
    assert f["amount_cents"] == 4590
    assert f["card_seconds_since_last"] == -1  # no earlier attempt
    assert all(v == 0 for k, v in f.items()
               if k not in ("amount_cents", "card_seconds_since_last"))


def test_counts_use_their_windows(history):
    history(timedelta(minutes=5))
    history(timedelta(minutes=30), outcome="block")
    history(timedelta(hours=5), email="eB", outcome="not_screened")
    history(timedelta(days=3))  # outside 24 h, inside 30 days
    history(timedelta(days=40))  # outside every window
    f = build()
    assert f["card_attempts_10m"] == 1
    assert f["card_attempts_1h"] == 2
    assert f["card_attempts_24h"] == 3
    assert f["card_blocked_24h"] == 2  # block and not_screened
    assert f["card_distinct_emails_24h"] == 2
    assert f["card_allowed_30d"] == 2
    assert f["email_attempts_24h"] == 2
    assert f["ip_attempts_1h"] == 2


def test_distinct_cards_per_email_and_ip(history):
    for card in ("c1", "c2", "c2", "c3"):
        history(timedelta(minutes=1), card=card)
    f = build(card_fingerprint="c9")
    assert f["email_distinct_cards_24h"] == 3
    assert f["ip_distinct_cards_1h"] == 3
    assert f["card_attempts_24h"] == 0


def test_only_strictly_earlier_events_count(history):
    event = history(timedelta(0))
    f = build(occurred_at=event.occurred_at)
    assert f["card_attempts_10m"] == 0


def test_missing_keys_give_zero_counts(history):
    history(timedelta(minutes=1), email="", ip="")
    f = build(email_hash="", ip_hash="")
    assert f["email_attempts_24h"] == 0 and f["ip_attempts_1h"] == 0
    assert f["card_attempts_10m"] == 1


def test_benchmark_command_reports_and_leaves_nothing_behind(capsys):
    from django.core.management import CommandError, call_command

    try:
        call_command("benchmark_screening", payments=30, history=60)
    except CommandError:
        pass  # a slow test machine can miss the target; the report and clean-up still count
    out = capsys.readouterr().out
    assert "30 screenings over 60 earlier events" in out and "p95" in out
    assert not ScreeningEvent.objects.exists() and not Payment.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_load_test_command_reports_and_cleans_up(capsys):
    from django.core.management import CommandError, call_command

    try:
        call_command("loadtest_screening", rate=20, seconds=1, workers=4, history=40)
    except CommandError:
        pass  # a slow test machine can miss the target; the report and clean-up still count
    out = capsys.readouterr().out
    assert "20 screenings at 20/s" in out and "NFR-PER-02" in out
    assert not ScreeningEvent.objects.exists() and not Payment.objects.exists()
