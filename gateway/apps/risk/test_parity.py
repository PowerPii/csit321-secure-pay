"""Parity: the gateway's SQL features equal the research replay the model is trained on.

One random event stream (shared cards, emails and IPs, same-time ties, every outcome, gaps
from seconds to 40 days) is written as ScreeningEvent rows and also replayed by
research/features/gateway_schema.py. For every event, SqlFeatures at that event's time must
give the same 16 values. If either side changes a definition, this fails.

Runs wherever the research folder sits next to the gateway (the repo, CI); skipped inside
the gateway image, which does not ship research/.
"""
import importlib.util
import math
import random
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from apps.payments.models import Payment
from apps.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, SqlFeatures
from apps.risk.models import ScreeningEvent
from apps.risk.pipeline import Attempt

pytestmark = pytest.mark.django_db

RESEARCH = Path(__file__).resolve().parents[3] / "research" / "features" / "gateway_schema.py"


@pytest.fixture(scope="module")
def research():
    if not RESEARCH.is_file():
        pytest.skip("research/ is not next to the gateway (e.g. inside the gateway image)")
    spec = importlib.util.spec_from_file_location("gateway_schema", RESEARCH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while defining
    spec.loader.exec_module(module)
    return module


def test_both_sides_agree_on_the_schema(research):
    assert research.FEATURE_SCHEMA_VERSION == FEATURE_SCHEMA_VERSION
    assert tuple(research.FEATURE_NAMES) == FEATURE_NAMES


def random_stream(rng, n):
    """(offset seconds, amount, card, email, ip, outcome); ties and long gaps on purpose."""
    gaps = [0, 0, 1, 30, 299, 300, 600, 3599, 3600, 7200, 86399, 86400, 3 * 86400,
            7 * 86400, 12 * 86400, 30 * 86400, 40 * 86400]
    t, rows = 0, []
    for _ in range(n):
        t += rng.choice(gaps[:9] * 4 + gaps)
        rows.append((t, rng.randint(100, 90_000), rng.choice(["c1", "c2", "c3", ""]),
                     rng.choice(["e1", "e2", "e3", ""]), rng.choice(["i1", "i2", ""]),
                     rng.choice(["allow"] * 5 + ["verify", "block", "not_screened"])))
    return rows


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_sql_features_equal_the_research_replay(research, shop, seed):
    rng = random.Random(seed)  # nosec B311 - test data
    rows = random_stream(rng, 120)
    base = timezone.now() - timedelta(seconds=rows[-1][0] + 60)
    for t, amount, card, email, ip, outcome in rows:
        payment = Payment.create_for_merchant(shop.merchant, order_reference="PARITY",
                                              amount=amount, return_url="https://shop.test/r")
        ScreeningEvent.objects.create(
            payment=payment, merchant=shop.merchant, occurred_at=base + timedelta(seconds=t),
            amount=amount, card_fingerprint=card, email_hash=email, ip_hash=ip, outcome=outcome)

    expected = research.replay(
        research.Event(at=float(t), amount_cents=a, card=c, email=e, ip=i, outcome=o)
        for t, a, c, e, i, o in rows)
    sql = SqlFeatures()
    for (t, amount, card, email, ip, _), want in zip(rows, expected, strict=True):
        got = sql.build(Attempt(attempt_id="pay_x", merchant_id="mer_x", amount_cents=amount,
                                card_fingerprint=card, email_hash=email, ip_hash=ip,
                                occurred_at=base + timedelta(seconds=t)))
        assert set(got) == set(want)
        for name in FEATURE_NAMES:
            assert math.isclose(got[name], want[name], rel_tol=1e-9, abs_tol=1e-9), (
                f"t={t} {name}: gateway {got[name]} research {want[name]}")
