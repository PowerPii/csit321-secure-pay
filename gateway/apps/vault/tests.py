import pytest

from apps.vault.fingerprint import card_fingerprint, last4


def test_fingerprint_is_stable_and_ignores_spacing():
    assert card_fingerprint("4111 1111 1111 1111", "k") == card_fingerprint("4111111111111111", "k")


def test_fingerprint_depends_on_key_and_hides_pan():
    fp = card_fingerprint("4111111111111111", "k1")
    assert fp != card_fingerprint("4111111111111111", "k2")
    assert "4111" not in fp


def test_last4_and_validation():
    assert last4("4111-1111-1111-1234") == "1234"
    with pytest.raises(ValueError):
        last4("123")
