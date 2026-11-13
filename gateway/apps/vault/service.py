"""The vault's interface. The only code that encrypts or decrypts card data.

    tokenise(...)  -> CardSummary   card entry (C3): encrypt, store, return token + summary
    take(token)    -> CardData|None submission: read, decrypt and delete in one step
    has(token)     -> bool          is the card still there (checked before screening)
    discard(token)                  the customer replaced the card, or the session ended

Nothing returned by `tokenise` contains the number or security code, so callers can store
and log the summary freely. `take` is the one place card data leaves the vault, to be sent
to the simulator once.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.carddata import luhn_ok
from apps.common.ids import new_id
from apps.vault.fingerprint import card_fingerprint
from apps.vault.models import StoredCard

DB = "vault"
CVC = re.compile(r"^[0-9]{3,4}$")


class CardRejected(ValueError):
    """The card details are not usable. `code` and `field` are safe to show; no card data."""

    def __init__(self, code: str, message: str, field: str):
        super().__init__(message)
        self.code, self.message, self.field = code, message, field


@dataclass(frozen=True)
class CardSummary:
    token: str
    brand: str
    last4: str
    fingerprint: str
    expiry_month: int
    expiry_year: int


@dataclass(frozen=True)
class CardData:
    number: str
    cvc: str
    expiry_month: int
    expiry_year: int

    def __repr__(self):  # never print card data, even by accident
        return f"CardData(****{self.number[-4:]})"


def brand_for(digits: str) -> str:
    if digits.startswith("4"):
        return "visa"
    if digits[:2] in {"51", "52", "53", "54", "55"} or 2221 <= int(digits[:4]) <= 2720:
        return "mastercard"
    if digits[:2] in {"34", "37"}:
        return "amex"
    return "unknown"


def _fernet() -> Fernet:
    return Fernet(settings.VAULT_ENCRYPTION_KEY)


def _int(value, field) -> int:
    if isinstance(value, bool):
        raise CardRejected("invalid_expiry", "Enter the expiry date as MM / YY.", field)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise CardRejected("invalid_expiry", "Enter the expiry date as MM / YY.", field) from None


def validate(number, expiry_month, expiry_year, cvc, today=None) -> CardData:
    if not isinstance(number, str):
        raise CardRejected("invalid_card_number", "Enter a valid card number.", "number")
    digits = re.sub(r"[ \-]", "", number)
    if not digits.isdigit() or not 13 <= len(digits) <= 19 or not luhn_ok(digits):
        raise CardRejected("invalid_card_number", "Enter a valid card number.", "number")
    month = _int(expiry_month, "expiry_month")
    year = _int(expiry_year, "expiry_year")
    if year < 100:
        year += 2000
    if not 1 <= month <= 12 or not 2000 <= year <= 2099:
        raise CardRejected("invalid_expiry", "Enter the expiry date as MM / YY.", "expiry_month")
    today = today or timezone.now().date()
    if (year, month) < (today.year, today.month):
        raise CardRejected("card_expired", "This card has expired.", "expiry_month")
    if not isinstance(cvc, str) or not CVC.match(cvc):
        raise CardRejected("invalid_cvc", "Enter the 3 or 4 digit security code.", "cvc")
    return CardData(number=digits, cvc=cvc, expiry_month=month, expiry_year=year)


def tokenise(number, expiry_month, expiry_year, cvc, *, expires_at: datetime) -> CardSummary:
    card = validate(number, expiry_month, expiry_year, cvc)
    secret_part = json.dumps({"number": card.number, "cvc": card.cvc}).encode()
    stored = StoredCard.objects.using(DB).create(
        token=new_id("tok"),
        ciphertext=_fernet().encrypt(secret_part).decode(),
        brand=brand_for(card.number),
        last4=card.number[-4:],
        expiry_month=card.expiry_month,
        expiry_year=card.expiry_year,
        fingerprint=card_fingerprint(card.number),
        expires_at=expires_at,
    )
    return CardSummary(token=stored.token, brand=stored.brand, last4=stored.last4,
                       fingerprint=stored.fingerprint, expiry_month=stored.expiry_month,
                       expiry_year=stored.expiry_year)


def take(token: str) -> CardData | None:
    """Return the card for this token and delete it, so it can be used exactly once."""
    with transaction.atomic(using=DB):
        stored = (StoredCard.objects.using(DB).select_for_update()
                  .filter(token=token, expires_at__gt=timezone.now()).first())
        if stored is None:
            return None
        secret_part = json.loads(_fernet().decrypt(stored.ciphertext.encode()))
        stored.delete()
    return CardData(number=secret_part["number"], cvc=secret_part["cvc"],
                    expiry_month=stored.expiry_month, expiry_year=stored.expiry_year)


def has(token: str) -> bool:
    """True if the card for this token is still in the vault (not taken, not expired)."""
    return bool(token) and StoredCard.objects.using(DB).filter(
        token=token, expires_at__gt=timezone.now()).exists()


def discard(token: str) -> None:
    if token:
        StoredCard.objects.using(DB).filter(token=token).delete()


def purge_expired() -> int:
    """Delete cards whose checkout ended without a submission. Run by the worker."""
    deleted, _ = StoredCard.objects.using(DB).filter(expires_at__lte=timezone.now()).delete()
    return deleted
