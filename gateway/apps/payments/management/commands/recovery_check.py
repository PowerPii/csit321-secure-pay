"""After a restore or a rollback: does the gateway still agree with the card network?

    python manage.py recovery_check                 # the 20 newest payments with an answer
    python manage.py recovery_check --payments 50
    python manage.py recovery_check --payment pay_... --payment SP-ABCD-1234

Changes nothing in the gateway. For each payment it asks the simulator about every finished
operation by its original operation ID (the same signed status query reconciliation uses,
never a new authorisation, capture or refund) and compares the answer with what the gateway
recorded. (Asking about an ID the simulator never saw retires that ID there, as the contract
says; a finished operation is never sent again anyway.)
It also checks that the vault holds no card that a backup could have brought back, and how
old the oldest open operation is.

Each line says PASS, WARN or FAIL; the exit code is 1 if anything FAILs. It prints payment
IDs, references and statuses only: never card data, keys or emails. Used by
deploy/recovery-check.sh, the restore drill and the rollback rehearsal (docs/RECOVERY.md).
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q
from django.utils import timezone

from apps.payments import processor
from apps.payments.models import Operation, Payment
from apps.vault import service as vault

# What the gateway stored for an operation, and the simulator answers that agree with it.
AGREES = {
    Operation.Status.SUCCEEDED: {"approved"},
    Operation.Status.FAILED: {"declined"},
    Operation.Status.NOT_PROCESSED: {"no_record"},
}
FINISHED = list(AGREES)


class Command(BaseCommand):
    help = "Check that recorded payments still agree with the simulator after a restore or rollback."

    def add_arguments(self, parser):
        parser.add_argument("--payments", type=int, default=20,
                            help="How many of the newest payments with an answer to check.")
        parser.add_argument("--payment", action="append", default=[],
                            help="A payment ID (pay_...) or reference (SP-...); repeatable.")

    def handle(self, *args, **options):
        logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per query otherwise
        self.failed = False
        self.check_vault()
        self.check_open_operations()
        self.check_payments(options["payment"], options["payments"])
        if self.failed:
            raise CommandError("recovery check FAILED (see above)")
        self.stdout.write("recovery check passed")

    def line(self, level, text):
        if level == "FAIL":
            self.failed = True
        self.stdout.write(f"{level:<5} {text}")

    def check_vault(self):
        # The worker purges expired cards on a schedule; allow it a few minutes.
        late = timezone.now() - timedelta(minutes=15)
        kept = vault.count_all()
        past = vault.count_expired(late)
        if past:
            self.line("FAIL", f"vault: {past} stored card(s) 15+ min past expiry (is the worker running?)")
        else:
            self.line("PASS", f"vault: {kept} card(s) held, all for checkouts still open")

    def check_open_operations(self):
        open_ops = Operation.objects.filter(status__in=Operation.OPEN_STATUSES)
        oldest = open_ops.order_by("created_at").values_list("created_at", flat=True).first()
        if oldest is None:
            self.line("PASS", "operations: none open")
            return
        age = (timezone.now() - oldest).total_seconds() / 60
        # Reconciliation escalates after about 38.5 minutes (NFR-AVA-03 bound: 1 hour).
        level = "PASS" if age < 40 else "WARN" if age < 60 else "FAIL"
        self.line(level, f"operations: {open_ops.count()} open, the oldest {age:.0f} min old "
                         f"(reconciliation settles them; the bound is 60 min)")

    def check_payments(self, wanted, limit):
        if wanted:
            payments = list(Payment.objects.filter(Q(public_id__in=wanted) | Q(reference__in=wanted)))
            missing = set(wanted) - {p.public_id for p in payments} - {p.reference for p in payments}
            for ref in sorted(missing):
                self.line("FAIL", f"{ref}: not found (was it made after the backup?)")
        else:
            payments = list(Payment.objects.annotate(
                done=Count("operations", filter=Q(operations__status__in=FINISHED)))
                .filter(done__gt=0).order_by("-created_at")[:limit])
        if not payments:
            self.line("WARN", "payments: none with a finished operation to compare")
            return
        agree = 0
        for payment in payments:
            ops = list(payment.operations.filter(status__in=FINISHED).order_by("created_at"))
            problems = []
            for op in ops:
                answer = processor.status_query(op)
                record = answer.record or {}
                seen = record.get("status")
                if answer.kind is processor.AnswerKind.NO_ANSWER:
                    problems.append(f"{op.type} {op.public_id}: no answer ({answer.problem})")
                elif seen not in AGREES[op.status]:
                    problems.append(f"{op.type} {op.public_id}: gateway says {op.status}, "
                                    f"simulator says {seen or answer.conflict_code}")
            if problems:
                for problem in problems:
                    self.line("FAIL", f"{payment.public_id} {payment.reference} ({payment.status}): {problem}")
            else:
                agree += 1
                self.line("PASS", f"{payment.public_id} {payment.reference} ({payment.status}): "
                                  f"{len(ops)} operation(s) agree with the simulator")
        self.line("PASS" if agree == len(payments) else "FAIL",
                  f"payments: {agree} of {len(payments)} agree with the simulator")
