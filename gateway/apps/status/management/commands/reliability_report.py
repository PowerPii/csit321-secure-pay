"""The user-facing reliability measures, for the final presentation and the M6 report.

    python manage.py reliability_report               # the last 24 hours
    python manage.py reliability_report --hours 168   # the last week
    python manage.py reliability_report --json        # the same numbers as /status.json

Read-only. Each number is printed with its population, window and environment, so a slide
can quote it honestly (docs/RELIABILITY-MEASURES.md). Counts only: no IDs, amounts or emails.
"""
import json

from django.core.management.base import BaseCommand

from apps.status.measures import build_measures


def _ms(value):
    return "n/a" if value is None else f"{value} ms"


def _age(seconds):
    if seconds is None:
        return "none"
    return f"{seconds // 60} min {seconds % 60} s"


class Command(BaseCommand):
    help = "Print the user-facing reliability measures with their populations and windows."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        m = build_measures(hours=options["hours"])
        if options["json"]:
            self.stdout.write(json.dumps(m, indent=2))
            return
        w, t, a = m["window"], m["checkout_time"], m["definite_answers"]
        s, o = m["screening_unavailable"], m["oldest_outstanding"]
        b = a["breakdown"]
        pct = "n/a" if a["percent"] is None else f"{a['percent']}%"
        lines = [
            f"Environment: {m['environment']}",
            (f"Window: {w['start']} to {w['end']} ({w['hours']} h; payments from the last "
            f"{w['settle_minutes']} min left out of the share)"),
            f"Population: {m['population']}",
            "",
            f"Checkout time ({t['definition']}):",
            f"  p50 {_ms(t['p50_ms'])}, p95 {_ms(t['p95_ms'])} over {t['count']} payments",
            "",
            f"Definite answers ({a['definition']}):",
            f"  {a['answered']} of {a['eligible']} = {pct}",
            (f"  approved {b['approved']}, declined by the bank {b['declined']}, "
            f"blocked on purpose {b['expected_block']} (fraud rules or model, failed or expired "
            f"code, amount limit)"),
            (f"  not answered: screening unavailable {b['screening_unavailable']}, request not "
            f"processed {b['not_processed']}, still unfinished {b['unfinished']}, other "
            f"blocks {b['other_block']}"),
            (f"  left out: waiting for the customer's code {a['excluded']['waiting_on_customer']}, "
            f"too recent {a['excluded']['too_recent']}"),
            "",
            f"Screening unavailable ({s['definition']}): {s['count']}",
            "",
            f"Oldest outstanding ({o['definition']}):",
            f"  card-network calls open {o['operations_open']}, oldest {_age(o['operation_age_seconds'])}",
            f"  webhooks waiting {o['webhooks_waiting']}, oldest {_age(o['webhook_age_seconds'])}",
        ]
        self.stdout.write("\n".join(lines))
