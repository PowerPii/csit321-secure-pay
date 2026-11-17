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


# --- Branded HTML emails (demo-day polish) ------------------------------------------------

def test_branded_backend_adds_escaped_html_and_keeps_the_text(settings):
    from django.core import mail
    from django.core.mail import get_connection, send_mail

    from apps.common.branded_email import BrandedEmailBackend

    settings.EMAIL_INNER_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    body = ("Thank you. Your payment to <Volt & Co.> was approved.\n\n"
            "Amount:     S$249.00\nReference:  SP-ABCD-1234\n\n"
            "https://gateway.example/guest/status?ref=SP-ABCD-1234\n")
    send_mail("Receipt", body, "a@example.com", ["b@example.com"],
              connection=get_connection("apps.common.branded_email.BrandedEmailBackend"))
    [sent] = mail.outbox
    assert sent.body == body
    [(html, kind)] = sent.alternatives
    assert kind == "text/html"
    assert "&lt;Volt &amp; Co.&gt;" in html and "<Volt" not in html
    assert ">Amount</td>" in html and "S$249.00" in html
    assert 'href="https://gateway.example/guest/status?ref=SP-ABCD-1234"' in html
    assert "TEST MODE" in html
    assert isinstance(get_connection("apps.common.branded_email.BrandedEmailBackend"),
                      BrandedEmailBackend)


def test_verification_code_is_shown_large():
    from apps.common.branded_email import html_for

    html = html_for("123456 is your SecurePay verification code",
                    "Your SecurePay verification code is 123456\n")
    assert "letter-spacing:8px" in html and ">123456</span>" in html
    assert "letter-spacing:8px" not in html_for("Receipt", "Hello\n")


def test_branded_email_carries_the_securepay_mark_inline(settings):
    """Sprint 12 branding kit: the mark is a related part shown by cid, not a download."""
    from email import message_from_bytes

    from django.core import mail
    from django.core.mail import EmailMessage, get_connection

    from apps.common.branded_email import LOGO_CID

    settings.EMAIL_INNER_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    connection = get_connection("apps.common.branded_email.BrandedEmailBackend")
    EmailMessage("Receipt", "Hello\n", "a@example.com", ["b@example.com"],
                 connection=connection).send()
    [sent] = mail.outbox
    parsed = message_from_bytes(sent.message().as_bytes())
    assert parsed.get_content_type() == "multipart/related"
    [image] = [p for p in parsed.walk() if p.get_content_type() == "image/png"]
    assert image["Content-ID"] == f"<{LOGO_CID}>"
    assert image.get_payload(decode=True).startswith(b"\x89PNG")
    [html] = [p for p in parsed.walk() if p.get_content_type() == "text/html"]
    assert f'src="cid:{LOGO_CID}"' in html.get_payload(decode=True).decode()

    # With a real attachment the email stays multipart/mixed and uses the text mark.
    mail.outbox = []
    with_file = EmailMessage("Report", "Hello\n", "a@example.com", ["b@example.com"],
                             connection=connection)
    with_file.attach("report.csv", "a,b\n", "text/csv")
    with_file.send()
    [sent] = mail.outbox
    assert message_from_bytes(sent.message().as_bytes()).get_content_type() == "multipart/mixed"
    assert "cid:" not in sent.alternatives[0][0]


def test_brand_kit_is_the_same_everywhere():
    """Sprint 12 branding kit: one mark and one colour set (frontend/brand) on every surface."""
    import json
    import re
    from pathlib import Path

    import pytest

    from apps.common import branded_email

    root = Path(__file__).resolve().parents[3]
    brand = root / "frontend" / "brand"
    if not brand.is_dir():
        pytest.skip("frontend/brand is not in this checkout (e.g. inside the gateway image)")
    mark = (brand / "securepay-mark.svg").read_text().strip()
    for app in ("checkout", "dashboard", "website"):
        favicon = (root / "frontend" / app / "public" / "favicon.svg").read_text().strip()
        assert favicon == mark, f"frontend/{app}/public/favicon.svg differs from the brand mark"
    brand_tsx = (root / "frontend" / "checkout" / "src" / "Brand.tsx").read_text()
    for shape in re.findall(r' d="([^"]+)"', mark):
        assert shape in brand_tsx, "Brand.tsx draws a different mark"

    tokens = json.loads((brand / "tokens.json").read_text())
    assert (branded_email.NAVY, branded_email.INK, branded_email.SAFFRON, branded_email.MUTED,
            branded_email.LINE, branded_email.PAPER) == (
        tokens["navy"], tokens["ink"], tokens["saffron"], tokens["muted"], tokens["line"],
        tokens["paper"])
    website = (root / "frontend" / "website" / "src" / "theme.ts").read_text()
    dashboard = (root / "frontend" / "dashboard" / "src" / "theme.ts").read_text()
    checkout = (root / "frontend" / "checkout" / "src" / "styles.css").read_text()
    for name in ("navy", "ink", "saffron", "paper", "line", "muted", "allow", "verify", "block"):
        assert tokens[name] in website, f"website theme lacks {name} {tokens[name]}"
    for name in ("navy", "ink", "saffron"):
        assert tokens[name] in dashboard and tokens[name] in checkout, name
