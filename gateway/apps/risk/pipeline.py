"""Fraud screening pipeline: features -> rules -> model -> policy.

Runs synchronously before the simulator call. Only uses information available before
submission. During early development `StubModel` stands in for the trained
HistGradientBoosting artefact loaded from `model_artifacts/`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from django.conf import settings

FEATURE_SCHEMA_VERSION = "fs-0.1"
POLICY_VERSION = "policy-0.1"


class Outcome(StrEnum):
    ALLOW = "allow"
    VERIFY = "verify"  # simulated verification code
    BLOCK = "block"


@dataclass(frozen=True)
class Attempt:
    """What the pipeline sees. Never contains a card number, only the fingerprint."""

    attempt_id: str
    merchant_id: str
    amount_cents: int
    card_fingerprint: str
    email_hash: str | None = None
    ip: str | None = None
    device_id: str | None = None


@dataclass
class Decision:
    outcome: Outcome
    score: float | None
    reasons: list[str] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)
    model_version: str | None = None
    policy_version: str = POLICY_VERSION
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    elapsed_ms: float = 0.0


class FeatureBuilder(Protocol):
    def build(self, attempt: Attempt) -> dict[str, float]: ...


class Model(Protocol):
    version: str

    def score(self, features: dict[str, float]) -> float: ...


class BasicFeatures:
    """Current-transaction features only. Prior-activity counts (per card fingerprint,
    email hash, IP and device in fixed windows) are added as indexed SQL counts over
    earlier screening events, mirroring research/features/."""

    def build(self, attempt: Attempt) -> dict[str, float]:
        return {"amount_cents": float(attempt.amount_cents)}


class StubModel:
    version = "stub-0"

    def score(self, features: dict[str, float]) -> float:
        return 0.0


@dataclass
class Rules:
    blocklisted_fingerprints: frozenset[str] = frozenset()
    verify_above_cents: int = 50_000  # S$500

    def evaluate(self, attempt: Attempt, features: dict[str, float]) -> tuple[Outcome | None, list[str]]:
        if attempt.card_fingerprint in self.blocklisted_fingerprints:
            return Outcome.BLOCK, ["blocklisted_card"]
        if attempt.amount_cents > settings.GATEWAY_RULES["MAX_AMOUNT_CENTS"]:
            return Outcome.BLOCK, ["amount_over_limit"]
        if features.get("attempts_card_1h", 0) >= 5:
            return Outcome.BLOCK, ["card_attempt_burst"]
        if attempt.amount_cents > self.verify_above_cents:
            return Outcome.VERIFY, ["high_amount"]
        return None, []


@dataclass
class Policy:
    verify_threshold: float = 0.5
    block_threshold: float = 0.9

    def decide(self, rule_outcome: Outcome | None, score: float) -> tuple[Outcome, list[str]]:
        if rule_outcome is Outcome.BLOCK:
            return Outcome.BLOCK, []
        if score >= self.block_threshold:
            return Outcome.BLOCK, ["model_score_high"]
        if rule_outcome is Outcome.VERIFY or score >= self.verify_threshold:
            return Outcome.VERIFY, [] if rule_outcome else ["model_score_medium"]
        return Outcome.ALLOW, []


class ScreeningUnavailable(Exception):
    pass


@dataclass
class Pipeline:
    features: FeatureBuilder = field(default_factory=BasicFeatures)
    rules: Rules = field(default_factory=Rules)
    model: Model = field(default_factory=StubModel)
    policy: Policy = field(default_factory=Policy)

    def screen(self, attempt: Attempt) -> Decision:
        start = time.perf_counter()
        try:
            feats = self.features.build(attempt)
            rule_outcome, reasons = self.rules.evaluate(attempt, feats)
            score = self.model.score(feats)
        except Exception as exc:  # any failure stops before a financial effect
            raise ScreeningUnavailable(str(exc)) from exc
        elapsed = (time.perf_counter() - start) * 1000
        if elapsed > settings.GATEWAY_RULES["SCREENING_TIMEOUT_MS"]:
            raise ScreeningUnavailable(f"screening took {elapsed:.0f} ms")
        outcome, more = self.policy.decide(rule_outcome, score)
        return Decision(
            outcome=outcome,
            score=score,
            reasons=reasons + more,
            features=feats,
            model_version=self.model.version,
            elapsed_ms=elapsed,
        )
