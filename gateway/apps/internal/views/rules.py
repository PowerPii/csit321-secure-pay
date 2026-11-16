"""Fraud rules (FR-FRD-02, FR-FRD-03; UC-37). Analysts and administrators read them;
administrators change them.

* GET  rules : the current rule set (enabled and switched-off rules), its version, whether an
  evaluation run has frozen it, and the features and operators a rule can use.
* GET  rules/{rule_id} : every revision of one rule, newest first.
* POST rules/check {rule} : the conflict warnings for a rule, without saving (FR-FRD-03).
* POST rules {rule, confirm_conflicts?} : add a rule. 409 rule_conflict lists the warnings.
* POST rules/{rule_id} {rule, confirm_conflicts?} : save a new revision.
* POST rules/{rule_id}/enabled {enabled} : switch a rule on or off (a new revision too).
* POST rules/freeze {note} and rules/unfreeze : start and end an evaluation run.
"""
from rest_framework import status
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import invalid, not_found
from apps.common.timefmt import rfc3339
from apps.internal.access import ADMIN, ANALYST_OR_ADMIN, StaffAPIView
from apps.risk import rulebook
from apps.risk.features import FEATURE_NAMES
from apps.risk.models import FraudRule


def rule_to_dict(rule: FraudRule) -> dict:
    return {
        "id": rule.rule_id, "revision": rule.revision, "code": rule.code,
        "description": rule.description or None, "feature": rule.feature, "op": rule.op,
        "value": rule.value, "action": rule.action, "enabled": rule.enabled,
        "condition": rulebook.describe(rulebook.spec_of(rule)),
        "created_at": rfc3339(rule.created_at), "created_by": rule.created_by or None,
        "superseded_at": rfc3339(rule.superseded_at),
        "ruleset_version": f"rules-0.{rule.ruleset_version}",
    }


def ruleset_dict() -> dict:
    state = rulebook._state()
    rules = rulebook.current_rules().order_by("-enabled", "code")
    return {
        "version": state.label,
        "frozen": ({"since": rfc3339(state.frozen_since), "by": state.frozen_by,
                    "note": state.freeze_note} if state.frozen_since else None),
        "rules": [rule_to_dict(r) for r in rules],
        "features": list(FEATURE_NAMES),
        "ops": [{"value": k, "label": v} for k, v in rulebook.OPS.items()],
        "fixed": ["Block list and review list matches", "Amount above the S$10,000 ceiling"],
    }


def _body(request) -> dict:
    return request.data if isinstance(request.data, dict) else {}


class _RulesView(StaffAPIView):
    def _audit(self, action, target_id, **details):
        audit(action, actor_type=AuditEvent.ActorType.STAFF, actor_id=self.staff.public_id,
              target_type="fraud_rule", target_id=target_id,
              request_id=self.request.request_id, details=details)


class RuleSetView(_RulesView):
    def get_permissions(self):
        self.roles = ANALYST_OR_ADMIN if self.request.method == "GET" else ADMIN
        return super().get_permissions()

    def get(self, request):
        return Response(ruleset_dict())

    def post(self, request):
        body = _body(request)
        spec = rulebook.validate(body.get("rule") if isinstance(body.get("rule"), dict) else {})
        rule, warnings = rulebook.save(self.staff.public_id, spec,
                                       confirm_conflicts=body.get("confirm_conflicts") is True)
        self._audit("fraud_rule.created", rule.rule_id, rule=spec,
                    ruleset_version=f"rules-0.{rule.ruleset_version}",
                    conflicts_accepted=[w["code"] for w in warnings])
        return Response({"rule": rule_to_dict(rule), "warnings": warnings, **ruleset_dict()},
                        status=status.HTTP_201_CREATED)


class RuleCheckView(_RulesView):
    roles = ADMIN

    def post(self, request):
        body = _body(request)
        spec = rulebook.validate(body.get("rule") if isinstance(body.get("rule"), dict) else {})
        rule_id = body.get("rule_id") if isinstance(body.get("rule_id"), str) else None
        return Response({"conflicts": rulebook.conflicts(spec, ignore_rule_id=rule_id)})


class RuleDetailView(_RulesView):
    def get_permissions(self):
        self.roles = ANALYST_OR_ADMIN if self.request.method == "GET" else ADMIN
        return super().get_permissions()

    def get(self, request, rule_id: str):
        revisions = FraudRule.objects.filter(rule_id=rule_id[:32]).order_by("-revision")
        if not revisions:
            raise not_found()
        return Response({"id": rule_id, "revisions": [rule_to_dict(r) for r in revisions]})

    def post(self, request, rule_id: str):
        body = _body(request)
        spec = rulebook.validate(body.get("rule") if isinstance(body.get("rule"), dict) else {})
        rule, warnings = rulebook.save(self.staff.public_id, spec, rule_id=rule_id[:32],
                                       confirm_conflicts=body.get("confirm_conflicts") is True)
        self._audit("fraud_rule.changed", rule.rule_id, revision=rule.revision, rule=spec,
                    ruleset_version=f"rules-0.{rule.ruleset_version}",
                    conflicts_accepted=[w["code"] for w in warnings])
        return Response({"rule": rule_to_dict(rule), "warnings": warnings, **ruleset_dict()})


class RuleEnabledView(_RulesView):
    roles = ADMIN

    def post(self, request, rule_id: str):
        enabled = _body(request).get("enabled")
        if not isinstance(enabled, bool):
            raise invalid("invalid_field", "'enabled' must be true or false.", param="enabled")
        rule = rulebook.set_enabled(self.staff.public_id, rule_id[:32], enabled)
        self._audit("fraud_rule.enabled" if enabled else "fraud_rule.disabled", rule.rule_id,
                    revision=rule.revision, ruleset_version=f"rules-0.{rule.ruleset_version}")
        return Response({"rule": rule_to_dict(rule), **ruleset_dict()})


class RuleFreezeView(_RulesView):
    roles = ADMIN

    def post(self, request):
        note = _body(request).get("note")
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 200:
            raise invalid("missing_field", "Say which evaluation run this is (up to 200 "
                          "characters).", param="note")
        state = rulebook.freeze(self.staff.public_id, note.strip())
        self._audit("fraud_rules.frozen", state.label, note=note.strip())
        return Response(ruleset_dict())


class RuleUnfreezeView(_RulesView):
    roles = ADMIN

    def post(self, request):
        state, ended = rulebook.unfreeze()
        self._audit("fraud_rules.unfrozen", state.label, **ended)
        return Response(ruleset_dict())
