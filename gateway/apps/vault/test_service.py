from datetime import date, timedelta

import pytest
from cryptography.exceptions import InvalidTag
from django.db import connections
from django.utils import timezone

from apps.vault import service as vault
from apps.vault.models import StoredCard

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


def later():
    return timezone.now() + timedelta(hours=1)


def test_tokenise_keeps_only_ciphertext_and_summary():
    summary = vault.tokenise("4242 4242 4242 4242", 12, 30, "987", expires_at=later())
    assert summary.token.startswith("tok_") and len(summary.token) == 28
    assert (summary.brand, summary.last4, summary.expiry_year) == ("visa", "4242", 2030)
    with connections["vault"].cursor() as cur:
        cur.execute("SELECT row_to_json(c)::text, ciphertext FROM vault_storedcard c")
        dump, ciphertext = cur.fetchone()
    # Only the ciphertext holds the number and code; it decrypts only with the vault key.
    assert "4242424242424242" not in dump and '"987"' not in dump
    assert ciphertext.startswith("k1.dk_")  # under the vault data key (FR-ADM-14)
    assert vault._decrypt(ciphertext, summary.token) == (
        b'{"number": "4242424242424242", "cvc": "987"}')
    assert "4242424242424242" not in repr(summary)


def test_ciphertext_is_bound_to_its_token():
    a = vault.tokenise("4242424242424242", 12, 2030, "123", expires_at=later())
    b = vault.tokenise("5555555555554444", 1, 2031, "456", expires_at=later())
    stored_a = StoredCard.objects.using("vault").get(token=a.token)
    # AES-256-GCM: a 256-bit key, a fresh nonce per card, and the token as associated data.
    assert len(vault._key()) == 32
    with pytest.raises(InvalidTag):
        vault._decrypt(stored_a.ciphertext, b.token)
    StoredCard.objects.using("vault").filter(token=b.token).update(ciphertext=stored_a.ciphertext)
    with pytest.raises(InvalidTag):
        vault.take(b.token)


def test_take_returns_the_card_once_and_deletes_it():
    summary = vault.tokenise("5555555555554444", 1, 2031, "123", expires_at=later())
    card = vault.take(summary.token)
    assert (card.number, card.cvc, card.expiry_month, card.expiry_year) == (
        "5555555555554444", "123", 1, 2031)
    assert "5555555555554444" not in repr(card)
    assert vault.take(summary.token) is None
    assert not StoredCard.objects.using("vault").exists()


def test_expired_token_cannot_be_taken_and_is_purged():
    summary = vault.tokenise("4242424242424242", 12, 2030, "123",
                             expires_at=timezone.now() - timedelta(seconds=1))
    assert vault.take(summary.token) is None
    assert vault.purge_expired() == 1


@pytest.mark.parametrize(("args", "code"), [
    (("4242424242424241", 12, 2030, "123"), "invalid_card_number"),
    (("4242", 12, 2030, "123"), "invalid_card_number"),
    ((4242424242424242, 12, 2030, "123"), "invalid_card_number"),
    (("4242424242424242", 13, 2030, "123"), "invalid_expiry"),
    (("4242424242424242", "x", 2030, "123"), "invalid_expiry"),
    (("4242424242424242", 10, 2026, "123"), "card_expired"),
    (("4242424242424242", 12, 2030, "12"), "invalid_cvc"),
])
def test_validation(args, code):
    with pytest.raises(vault.CardRejected) as err:
        vault.validate(*args, today=date(2026, 11, 13))
    assert err.value.code == code
    assert "4242424242424242" not in err.value.message


def test_brands():
    assert vault.brand_for("4242424242424242") == "visa"
    assert vault.brand_for("2223003122003222") == "mastercard"
    assert vault.brand_for("378282246310005") == "amex"
    assert vault.brand_for("6011111111111117") == "unknown"
