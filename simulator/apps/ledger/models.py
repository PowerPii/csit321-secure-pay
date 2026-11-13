"""Balanced fictional ledger entries (SIMULATOR-CONTRACT.md section 4).

Each approved operation writes entries that sum to zero, in the same transaction as its
operation record. Declined operations write none. Internal to the simulator.
"""
from django.db import models


class LedgerEntry(models.Model):
    class Account(models.TextChoices):
        CARDHOLDER_AVAILABLE = "cardholder_available"
        CARDHOLDER_HELD = "cardholder_held"
        MERCHANT_SETTLEMENT = "merchant_settlement"

    operation_id = models.CharField(max_length=32, db_index=True)
    authorisation_id = models.CharField(max_length=32, db_index=True)
    kind = models.CharField(max_length=16)  # hold, release, charge, refund
    account = models.CharField(max_length=32, choices=Account.choices)
    amount = models.IntegerField()  # cents; entries of one operation sum to zero
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.operation_id} {self.kind} {self.account} {self.amount}"


def post_hold(operation_id: str, authorisation_id: str, amount: int) -> None:
    """An approved authorisation moves `amount` from available to held."""
    LedgerEntry.objects.bulk_create([
        LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id, kind="hold",
                    account=LedgerEntry.Account.CARDHOLDER_AVAILABLE, amount=-amount),
        LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id, kind="hold",
                    account=LedgerEntry.Account.CARDHOLDER_HELD, amount=amount),
    ])


def post_capture(operation_id: str, authorisation_id: str, authorised: int, amount: int) -> None:
    """Charge `amount` from the hold to the merchant and release the rest to the cardholder."""
    entries = [
        LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id, kind="charge",
                    account=LedgerEntry.Account.CARDHOLDER_HELD, amount=-amount),
        LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id, kind="charge",
                    account=LedgerEntry.Account.MERCHANT_SETTLEMENT, amount=amount),
    ]
    rest = authorised - amount
    if rest:
        entries += [
            LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id,
                        kind="release", account=LedgerEntry.Account.CARDHOLDER_HELD, amount=-rest),
            LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id,
                        kind="release", account=LedgerEntry.Account.CARDHOLDER_AVAILABLE,
                        amount=rest),
        ]
    LedgerEntry.objects.bulk_create(entries)


def post_release(operation_id: str, authorisation_id: str, amount: int) -> None:
    """A cancel gives the whole hold back to the cardholder."""
    LedgerEntry.objects.bulk_create([
        LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id,
                    kind="release", account=LedgerEntry.Account.CARDHOLDER_HELD, amount=-amount),
        LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id,
                    kind="release", account=LedgerEntry.Account.CARDHOLDER_AVAILABLE,
                    amount=amount),
    ])


def post_refund(operation_id: str, authorisation_id: str, amount: int) -> None:
    """A refund moves `amount` from the merchant back to the cardholder."""
    LedgerEntry.objects.bulk_create([
        LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id,
                    kind="refund", account=LedgerEntry.Account.MERCHANT_SETTLEMENT,
                    amount=-amount),
        LedgerEntry(operation_id=operation_id, authorisation_id=authorisation_id,
                    kind="refund", account=LedgerEntry.Account.CARDHOLDER_AVAILABLE,
                    amount=amount),
    ])
