"""Feature schema fs-0.1: what screening knows about an attempt at the moment it is submitted.

Current-attempt features plus prior-activity counts over earlier `ScreeningEvent` rows keyed
by card fingerprint, email hash and IP hash, in fixed windows. Only events strictly before
this attempt are counted (architecture section 7), so the same definitions can be replayed
on historical data without leaking the future.

`FEATURE_NAMES` is the contract with the model: a trained artefact's manifest lists the
features it was trained on, and the loader refuses an artefact that asks for a feature
this schema does not produce (apps.risk.scoring). Add a feature here, bump the version,
and mirror it in research/features/ so the parity test can compare both.
"""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q

from apps.risk.models import ScreeningEvent, ScreeningOutcome

FEATURE_SCHEMA_VERSION = "fs-0.1"

FEATURE_NAMES: tuple[str, ...] = (
    "amount_cents",
    "card_attempts_10m",
    "card_attempts_1h",
    "card_attempts_24h",
    "card_blocked_24h",
    "card_distinct_emails_24h",
    "card_allowed_30d",
    "email_attempts_24h",
    "email_distinct_cards_24h",
    "ip_attempts_1h",
    "ip_distinct_cards_1h",
)

BLOCKED = (ScreeningOutcome.BLOCK, ScreeningOutcome.NOT_SCREENED)


class SqlFeatures:
    """Indexed counts in three queries (card, email, IP), one round trip each."""

    def build(self, attempt) -> dict[str, float]:
        now = attempt.occurred_at
        m10, h1, h24, d30 = (now - timedelta(minutes=10), now - timedelta(hours=1),
                             now - timedelta(hours=24), now - timedelta(days=30))
        before = ScreeningEvent.objects.filter(occurred_at__lt=now)
        features = {name: 0.0 for name in FEATURE_NAMES}
        features["amount_cents"] = float(attempt.amount_cents)

        if attempt.card_fingerprint:
            card = before.filter(card_fingerprint=attempt.card_fingerprint,
                                 occurred_at__gte=d30).aggregate(
                card_attempts_10m=Count("id", filter=Q(occurred_at__gte=m10)),
                card_attempts_1h=Count("id", filter=Q(occurred_at__gte=h1)),
                card_attempts_24h=Count("id", filter=Q(occurred_at__gte=h24)),
                card_blocked_24h=Count("id", filter=Q(occurred_at__gte=h24,
                                                      outcome__in=BLOCKED)),
                card_distinct_emails_24h=Count("email_hash", distinct=True,
                                               filter=Q(occurred_at__gte=h24)
                                               & ~Q(email_hash="")),
                card_allowed_30d=Count("id", filter=Q(outcome=ScreeningOutcome.ALLOW)),
            )
            features.update({k: float(v) for k, v in card.items()})

        if attempt.email_hash:
            email = before.filter(email_hash=attempt.email_hash, occurred_at__gte=h24).aggregate(
                email_attempts_24h=Count("id"),
                email_distinct_cards_24h=Count("card_fingerprint", distinct=True,
                                               filter=~Q(card_fingerprint="")),
            )
            features.update({k: float(v) for k, v in email.items()})

        if attempt.ip_hash:
            ip = before.filter(ip_hash=attempt.ip_hash, occurred_at__gte=h1).aggregate(
                ip_attempts_1h=Count("id"),
                ip_distinct_cards_1h=Count("card_fingerprint", distinct=True,
                                           filter=~Q(card_fingerprint="")),
            )
            features.update({k: float(v) for k, v in ip.items()})
        return features
