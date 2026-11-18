"""Add plain-language explanations to decision records made before they existed.

    python manage.py explain_decisions [--all] [--dry-run]

Screening has stored an explanation with every decision since explanations were added
(apps.risk.explain). This fills in older records from what each one already holds: its reasons,
its feature values and its score. Model contributions are added only when the record was
scored by the model that is installed now (same version), so an explanation never describes a
different model from the one that made the decision; otherwise the record gets the rule part
only. Rule sentences use the current rule set; a rule that has since been removed keeps its code.

Only the explanation field changes: the decision, score, reasons and versions stay as they
were. --all redoes records that already have one. Unscreened attempts are left alone.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.risk import explain
from apps.risk.models import ScreeningEvent, ScreeningOutcome
from apps.risk.pipeline import explain_model
from apps.risk.rulebook import current_rule_set
from apps.risk.scoring import active_model

BATCH = 500


class Command(BaseCommand):
    help = "Fill in plain-language explanations on older screening decision records."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Redo records that have one.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, all=False, dry_run=False, **options):
        model = active_model()
        _, specs = current_rule_set()
        rules = {r.code: (r.feature, r.op, r.value) for r in specs}
        events = ScreeningEvent.objects.exclude(outcome=ScreeningOutcome.NOT_SCREENED)
        if not all:
            events = events.filter(explanation={})
        done = with_model = 0
        pending = []
        for event in events.order_by("id").iterator(chunk_size=BATCH):
            features = dict(event.features or {})
            same_model = bool(features) and event.model_version == model.version
            try:
                contributions = explain_model(model, features) if same_model else None
            except KeyError:  # an older feature schema without a feature this model reads
                contributions = None
            event.explanation = explain.explain(
                outcome=event.outcome, reasons=list(event.reasons or []), features=features,
                amount_cents=event.amount, score=event.score, contributions=contributions,
                rules=rules, max_amount=settings.GATEWAY_RULES["MAX_AMOUNT_CENTS"])
            with_model += contributions is not None
            done += 1
            pending.append(event)
            if len(pending) >= BATCH and not dry_run:
                ScreeningEvent.objects.bulk_update(pending, ["explanation"])
                pending = []
        if pending and not dry_run:
            ScreeningEvent.objects.bulk_update(pending, ["explanation"])
        verb = "Would explain" if dry_run else "Explained"
        self.stdout.write(f"{verb} {done} decision records ({with_model} with model "
                          f"contributions from {model.version}).")
