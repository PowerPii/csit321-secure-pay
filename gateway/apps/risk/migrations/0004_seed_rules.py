"""Seed the rule set with the two rules that were hard-coded in rules-0.1 (FR-FRD-02)."""
from django.db import migrations

SEED = [
    ("frl_seedcardattemptburst00", "card_attempt_burst",
     "Five or more earlier attempts with the same card in 10 minutes", "card_attempts_10m",
     "gte", 5, "block"),
    ("frl_seedhighamount000000000", "high_amount", "Amount above S$500 needs a verification code",
     "amount_cents", "gt", 50_000, "verify"),
]


def seed(apps, schema_editor):
    RuleSetState = apps.get_model("risk", "RuleSetState")
    FraudRule = apps.get_model("risk", "FraudRule")
    RuleSetState.objects.get_or_create(pk=1, defaults={"version": 1})
    for rule_id, code, description, feature, op, value, action in SEED:
        FraudRule.objects.get_or_create(
            rule_id=rule_id, revision=1,
            defaults={"code": code, "description": description, "feature": feature, "op": op,
                      "value": value, "action": action, "enabled": True,
                      "ruleset_version": 1})


class Migration(migrations.Migration):
    dependencies = [("risk", "0003_fraud_rules_and_blocklist")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
