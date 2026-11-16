"""Administrator-editable fraud rules (FR-FRD-02, FR-FRD-03; UC-37).

    current_rule_set() -> (version label, tuple[RuleSpec])   used by screening
    validate(body) -> dict                                     a rule from the dashboard
    conflicts(spec, ignore_rule_id) -> list[dict]              FR-FRD-03 warnings
    save(staff, spec, rule_id=None) / set_enabled(...)         new revision, version + 1
    freeze(staff, note) / unfreeze(staff)                      evaluation runs

A rule is a condition on one screening feature (`feature op value`) and an action. Rules apply
to payments screened after the change; earlier screening records keep the rules_version they
were decided with. Changing a rule adds a revision and never edits one, so every earlier
version stays readable. While an evaluation run is in progress the rule set is frozen and
every change is refused (UC-37).

Two rules conflict when their conditions on the same feature can both be true for one
payment and their actions differ (the block hides the verification), or when they are the
same condition twice. Conflicts are warnings: saving needs `confirm_conflicts: true`.
"""
import math
import re

from django.db import transaction
from django.utils import timezone

from apps.common.errors import ApiError, invalid
from apps.common.ids import new_id
from apps.risk.features import FEATURE_NAMES
from apps.risk.models import FraudRule, RuleSetState
from apps.risk.pipeline import DEFAULT_RULES, RULES_VERSION, RuleSpec

OPS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}
CODE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
# Reason codes the gateway itself records; a rule may not reuse them.
RESERVED_CODES = {"amount_over_limit", "screening_unavailable", "model_score_high",
                  "model_score_medium", "blocklisted_card", "blocklisted_email",
                  "blocklisted_ip", "review_list_card", "review_list_email", "review_list_ip"}


SEED_IDS = {"card_attempt_burst": "frl_seedcardattemptburst00",
            "high_amount": "frl_seedhighamount000000000"}
SEED_TEXT = {"card_attempt_burst": "Five or more earlier attempts with the same card in 10 "
                                   "minutes",
             "high_amount": "Amount above S$500 needs a verification code"}


def ensure_seeded() -> None:
    """The seeded rule set (migration 0004), recreated if the tables were emptied."""
    with transaction.atomic():
        _, created = RuleSetState.objects.get_or_create(pk=1)
        if created and not FraudRule.objects.exists():
            for spec in DEFAULT_RULES:
                FraudRule.objects.create(
                    rule_id=SEED_IDS[spec.code], revision=1, code=spec.code,
                    description=SEED_TEXT[spec.code], feature=spec.feature, op=spec.op,
                    value=spec.value, action=spec.action, ruleset_version=1)


def _state(lock=False) -> RuleSetState:
    ensure_seeded()
    states = RuleSetState.objects.select_for_update() if lock else RuleSetState.objects
    return states.get(pk=1)


def current_rules():
    return FraudRule.objects.filter(superseded_at__isnull=True)


def spec_of(rule: FraudRule) -> RuleSpec:
    return RuleSpec(rule.code, rule.feature, rule.op, rule.value, rule.action)


def current_rule_set() -> tuple[str, tuple[RuleSpec, ...]]:
    state = RuleSetState.objects.filter(pk=1).first()
    if state is None:  # never seeded (or emptied): rules-0.1, without writing during screening
        return RULES_VERSION, DEFAULT_RULES
    rules = current_rules().filter(enabled=True).order_by("rule_id")
    return state.label, tuple(spec_of(r) for r in rules)


def validate(body: dict) -> dict:
    code = body.get("code")
    if not isinstance(code, str) or not CODE.match(code) or code in RESERVED_CODES:
        raise invalid("invalid_field", "The reason code must be 3 to 48 lower-case letters, "
                      "digits or underscores, start with a letter and not be a built-in code.",
                      param="code")
    feature = body.get("feature")
    if feature not in FEATURE_NAMES:
        raise invalid("invalid_field", "Choose one of the screening features.", param="feature")
    op = body.get("op")
    if op not in OPS:
        raise invalid("invalid_field", "'op' must be gt, gte, lt, lte or eq.", param="op")
    value = body.get("value")
    if (not isinstance(value, int | float) or isinstance(value, bool)
            or not math.isfinite(value) or abs(value) > 1e12):
        raise invalid("invalid_field", "'value' must be a number.", param="value")
    action = body.get("action")
    if action not in ("block", "verify"):
        raise invalid("invalid_field", "'action' must be block or verify.", param="action")
    description = body.get("description") or ""
    if not isinstance(description, str) or len(description) > 200:
        raise invalid("invalid_field", "The description is at most 200 characters.",
                      param="description")
    return {"code": code, "feature": feature, "op": op, "value": float(value),
            "action": action, "description": description.strip()}


def _interval(op: str, value: float) -> tuple[float, bool, float, bool]:
    """(low, low_inclusive, high, high_inclusive) of the values the condition accepts."""
    inf = math.inf
    return {"gt": (value, False, inf, False), "gte": (value, True, inf, False),
            "lt": (-inf, False, value, False), "lte": (-inf, False, value, True),
            "eq": (value, True, value, True)}[op]


def _overlap(a: tuple, b: tuple) -> bool:
    low, low_in = max((a[0], a[1]), (b[0], b[1]), key=lambda x: (x[0], not x[1]))
    high, high_in = min((a[2], a[3]), (b[2], b[3]), key=lambda x: (x[0], x[1]))
    return low < high or (low == high and low_in and high_in)


def describe(spec) -> str:
    value = spec["value"] if isinstance(spec, dict) else spec.value
    feature = spec["feature"] if isinstance(spec, dict) else spec.feature
    op = spec["op"] if isinstance(spec, dict) else spec.op
    shown = int(value) if float(value).is_integer() else value
    return f"{feature} {OPS[op]} {shown}"


def conflicts(spec: dict, ignore_rule_id: str | None = None) -> list[dict]:
    found = []
    mine = _interval(spec["op"], spec["value"])
    for rule in current_rules().filter(enabled=True, feature=spec["feature"]):
        if rule.rule_id == ignore_rule_id:
            continue
        theirs = _interval(rule.op, rule.value)
        if not _overlap(mine, theirs):
            continue
        if (rule.op, rule.value, rule.action) == (spec["op"], spec["value"], spec["action"]):
            kind, message = "duplicate", "does the same as"
        elif rule.action != spec["action"]:
            kind = "opposite_action"
            message = ("can apply to the same payments as" if spec["action"] == "block"
                       else "is hidden, where both apply, by")
        else:
            continue
        found.append({"rule_id": rule.rule_id, "code": rule.code, "kind": kind,
                      "message": f"{describe(spec)} ({spec['action']}) {message} "
                                 f"{rule.code}: {describe(spec_of(rule))} ({rule.action})."})
    return found


def _check_not_frozen(state: RuleSetState) -> None:
    if state.frozen_since is not None:
        raise ApiError(409, "rules_frozen", "An evaluation run is in progress, so the fraud "
                       "rules cannot change until it ends.")


def _code_taken(code: str, rule_id: str | None) -> bool:
    return current_rules().filter(code=code).exclude(rule_id=rule_id or "").exists()


def save(staff_id: str, spec: dict, rule_id: str | None = None,
         confirm_conflicts: bool = False) -> tuple[FraudRule, list[dict]]:
    """Add a rule, or a new revision of `rule_id`. Returns it and the warnings accepted."""
    with transaction.atomic():
        state = _state(lock=True)
        _check_not_frozen(state)
        previous = None
        if rule_id:
            previous = current_rules().select_for_update().filter(rule_id=rule_id).first()
            if previous is None:
                raise ApiError(404, "resource_not_found", "No such rule.")
        if _code_taken(spec["code"], rule_id):
            raise invalid("invalid_field", "Another rule already uses this reason code.",
                          param="code")
        warnings = conflicts(spec, ignore_rule_id=rule_id)
        if warnings and not confirm_conflicts:
            raise ApiError(409, "rule_conflict", "This rule conflicts with an existing rule. "
                           "Check the warnings and save again to keep it.",
                           extra={"conflicts": warnings})
        state.version += 1
        state.save(update_fields=["version"])
        now = timezone.now()
        if previous is not None:
            previous.superseded_at = now
            previous.save(update_fields=["superseded_at"])
        rule = FraudRule.objects.create(
            rule_id=rule_id or new_id("frl"),
            revision=(previous.revision + 1) if previous else 1,
            enabled=previous.enabled if previous else True,
            created_by=staff_id, ruleset_version=state.version, **spec)
    return rule, warnings


def set_enabled(staff_id: str, rule_id: str, enabled: bool) -> FraudRule:
    with transaction.atomic():
        state = _state(lock=True)
        _check_not_frozen(state)
        previous = current_rules().select_for_update().filter(rule_id=rule_id).first()
        if previous is None:
            raise ApiError(404, "resource_not_found", "No such rule.")
        if previous.enabled == enabled:
            return previous
        state.version += 1
        state.save(update_fields=["version"])
        previous.superseded_at = timezone.now()
        previous.save(update_fields=["superseded_at"])
        return FraudRule.objects.create(
            rule_id=previous.rule_id, revision=previous.revision + 1, code=previous.code,
            description=previous.description, feature=previous.feature, op=previous.op,
            value=previous.value, action=previous.action, enabled=enabled,
            created_by=staff_id, ruleset_version=state.version)


def freeze(staff_id: str, note: str) -> RuleSetState:
    with transaction.atomic():
        state = _state(lock=True)
        if state.frozen_since is not None:
            raise ApiError(409, "rules_frozen", "An evaluation run is already in progress.")
        state.frozen_since, state.frozen_by, state.freeze_note = timezone.now(), staff_id, note
        state.save(update_fields=["frozen_since", "frozen_by", "freeze_note"])
    return state


def unfreeze() -> tuple[RuleSetState, dict]:
    with transaction.atomic():
        state = _state(lock=True)
        if state.frozen_since is None:
            raise ApiError(409, "rules_not_frozen", "No evaluation run is in progress.")
        ended = {"frozen_since": state.frozen_since.isoformat(), "note": state.freeze_note}
        state.frozen_since, state.frozen_by, state.freeze_note = None, "", ""
        state.save(update_fields=["frozen_since", "frozen_by", "freeze_note"])
    return state, ended
