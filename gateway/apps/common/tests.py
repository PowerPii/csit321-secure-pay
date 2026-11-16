import re

import pytest

from apps.common.carddata import contains_card_number, looks_like_card_number, luhn_ok
from apps.common.ids import new_id, new_reference


def test_ids_follow_the_contract_format():
    assert re.fullmatch(r"pay_[0-9A-Za-z]{24}", new_id("pay"))
    assert re.fullmatch(r"SP-[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}", new_reference("SP"))
    assert len({new_id("pay") for _ in range(1000)}) == 1000


@pytest.mark.parametrize("text", [
    "4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111",
    "card 5555555555554444 thanks", "378282246310005",
])
def test_card_numbers_are_detected(text):
    assert looks_like_card_number(text)


@pytest.mark.parametrize("text", [
    "4111111111111112",  # fails Luhn
    "ORD-10042", "123456789012",  # too short
    "2026-11-13T04:30:00Z", "+65 6123 4567",
])
def test_ordinary_text_is_not_a_card_number(text):
    assert not looks_like_card_number(text)


def test_nested_values_and_keys_are_searched():
    assert contains_card_number({"meta": {"notes": ["x", "4242 4242 4242 4242"]}})
    assert contains_card_number({"4242424242424242": 1})
    assert not contains_card_number({"amount": 4242424242424242})  # numbers are not text


def test_luhn():
    assert luhn_ok("79927398713")
    assert not luhn_ok("79927398710")


@pytest.mark.parametrize("enabled", [True, False])
def test_django_admin_is_routed_only_when_enabled(settings, enabled):
    """Production runs with the admin off (deploy/compose.prod.yaml): /admin/ must not resolve."""
    import importlib

    from django.urls import Resolver404, clear_url_caches, resolve

    import config.urls

    original = settings.ADMIN_ENABLED
    settings.ADMIN_ENABLED = enabled
    try:
        importlib.reload(config.urls)
        clear_url_caches()
        if enabled:
            assert resolve("/admin/login/").app_name == "admin"
        else:
            with pytest.raises(Resolver404):
                resolve("/admin/login/")
    finally:
        settings.ADMIN_ENABLED = original
        importlib.reload(config.urls)
        clear_url_caches()
