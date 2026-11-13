"""Fraud screening pipeline: features -> rules -> model -> policy (architecture section 7).

Runs synchronously when the customer pays, before anything reaches the simulator, and only
uses information available at that moment. Every stage is swappable for tests and for the
trained model:

    features  apps.risk.features.SqlFeatures   prior-activity counts (fs-0.1)
    lists     DbRiskLists                      seeded block / review lists
    rules     Rules                            deterministic, versioned (rules-0.1)
    model     apps.risk.scoring.active_model() StubModel until an artefact is installed
    policy    Policy                           versioned thresholds; an artefact may ship its own

Any failure, or a run longer than the budget (GATEWAY_RULES["SCREENING_TIMEOUT_MS"], 500 ms
by FR-FRD-04), raises ScreeningUnavailable. The caller blocks the attempt as
"screening_unavailable", never as fraud.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from django.conf import settings

from apps.risk.features import FEATURE_SCHEMA_VERSION, SqlFeatures
from apps.risk.scoring import Model, Thresholds, active_model

RULES_VERSION = "rules-0.1"
DEFAULT_POLICY = Thresholds(version="policy-0.1", verify_threshold=0.5, block_threshold=0.9)


class Outcome(StrEnum):
    ALLOW = "allow"
    VERIFY = "verify"  # simulated verification code (FR-CHK-05)
    BLOCK = "block"


@dataclass(frozen=True)
class Attempt:
    """What the pipeline sees. Never a card number: the vault fingerprint and keyed hashes."""

    attempt_id: str
    merchant_id: str
    amount_cents: int
    card_fingerprint: str
    occurred_at: datetime
    email_hash: str = ""
    ip_hash: str = ""
    device_hash: str = ""


@dataclass
class Decision:
    outcome: Outcome
    score: float | None
    reasons: list[str] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)
    model_version: str | None = None
    rules_version: str = RULES_VERSION
    policy_version: str = DEFAULT_POLICY.version
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    elapsed_ms: float = 0.0
    by_rule: bool = False  # a rule (not the model) caused a block or a verification

    @property
    def block_reason(self) -> str:
        """The payment's outcome reason when this decision blocks (contract OutcomeReason)."""
        if self.by_rule:
            return "amount_limit" if self.reasons == ["amount_over_limit"] else "fraud_rule"
        return "fraud_model"


class FeatureBuilder(Protocol):
    def build(self, attempt: Attempt) -> dict[str, float]: ...


@dataclass(frozen=True)
class ListHit:
    kind: str  # card, email, ip
    action: str  # block or verify
    label: str


class RiskLists(Protocol):
    def lookup(self, attempt: Attempt) -> list[ListHit]: ...


class DbRiskLists:
    def lookup(self, attempt: Attempt) -> list[ListHit]:
        from django.db.models import Q

        from apps.risk.models import RiskListEntry

        keys = [("card", attempt.card_fingerprint), ("email", attempt.email_hash),
                ("ip", attempt.ip_hash)]
        query = Q()
        for kind, value in keys:
            if value:
                query |= Q(kind=kind, value_hash=value)
        if not query:
            return []
        return [ListHit(kind, action, label) for kind, action, label in
                RiskListEntry.objects.filter(query, active=True)
                .values_list("kind", "action", "label")]


@dataclass
class Rules:
    """rules-0.1. Hard-coded in the MVP; admin-editable rules (FR-FRD-02) come later."""

    burst_attempts_10m: int = 5  # earlier attempts with the same card in 10 minutes -> block
    verify_above_cents: int = 50_000  # S$500 -> simulated verification

    def evaluate(self, attempt: Attempt, features: dict[str, float],
                 hits: list[ListHit]) -> tuple[Outcome | None, list[str]]:
        blocks, verifies = [], []
        for hit in hits:
            (blocks if hit.action == "block" else verifies).append(
                f"{'blocklisted' if hit.action == 'block' else 'review_list'}_{hit.kind}")
        if attempt.amount_cents > settings.GATEWAY_RULES["MAX_AMOUNT_CENTS"]:
            blocks.append("amount_over_limit")
        if features.get("card_attempts_10m", 0) >= self.burst_attempts_10m:
            blocks.append("card_attempt_burst")
        if attempt.amount_cents > self.verify_above_cents:
            verifies.append("high_amount")
        if blocks:
            return Outcome.BLOCK, sorted(set(blocks))
        if verifies:
            return Outcome.VERIFY, sorted(set(verifies))
        return None, []


@dataclass
class Policy:
    thresholds: Thresholds = DEFAULT_POLICY

    @property
    def version(self) -> str:
        return self.thresholds.version

    def decide(self, rule_outcome: Outcome | None, score: float) -> tuple[Outcome, list[str]]:
        if rule_outcome is Outcome.BLOCK:
            return Outcome.BLOCK, []
        if score >= self.thresholds.block_threshold:
            return Outcome.BLOCK, ["model_score_high"]
        if rule_outcome is Outcome.VERIFY:
            return Outcome.VERIFY, []
        if score >= self.thresholds.verify_threshold:
            return Outcome.VERIFY, ["model_score_medium"]
        return Outcome.ALLOW, []


class ScreeningUnavailable(Exception):
    pass


@dataclass
class Pipeline:
    features: FeatureBuilder = field(default_factory=SqlFeatures)
    lists: RiskLists = field(default_factory=DbRiskLists)
    rules: Rules = field(default_factory=Rules)
    model: Model = field(default_factory=active_model)
    policy: Policy | None = None  # None: the model's own thresholds, else policy-0.1

    def screen(self, attempt: Attempt) -> Decision:
        budget_ms = settings.GATEWAY_RULES["SCREENING_TIMEOUT_MS"]
        start = time.perf_counter()
        try:
            feats = self.features.build(attempt)
            hits = self.lists.lookup(attempt)
            rule_outcome, reasons = self.rules.evaluate(attempt, feats, hits)
            score = float(self.model.score(feats))
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"model score {score} outside [0, 1]")
        except Exception as exc:  # any failure stops before a financial effect
            raise ScreeningUnavailable(type(exc).__name__) from exc
        elapsed = (time.perf_counter() - start) * 1000
        if elapsed > budget_ms:
            raise ScreeningUnavailable(f"timeout after {elapsed:.0f} ms (budget {budget_ms} ms)")
        policy = self.policy or Policy(self.model.policy or DEFAULT_POLICY)
        outcome, more = policy.decide(rule_outcome, score)
        return Decision(
            outcome=outcome,
            score=score,
            reasons=reasons + more,
            features=feats,
            model_version=self.model.version,
            policy_version=policy.version,
            elapsed_ms=round(elapsed, 2),
            by_rule=outcome is not Outcome.ALLOW and not more,
        )
