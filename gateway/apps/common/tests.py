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
    """Slate rebrand (19 Nov 2026): one wordmark, one s. mark and one colour set
    (frontend/brand) on every surface."""
    import json
    from pathlib import Path

    import pytest

    from apps.common import branded_email
    from apps.guest import receipts

    root = Path(__file__).resolve().parents[3]
    brand = root / "frontend" / "brand"
    if not brand.is_dir():
        pytest.skip("frontend/brand is not in this checkout (e.g. inside the gateway image)")
    mark = (brand / "securepay-mark.svg").read_text().strip()
    for app in ("checkout", "dashboard", "website"):
        favicon = (root / "frontend" / app / "public" / "favicon.svg").read_text().strip()
        assert favicon == mark, f"frontend/{app}/public/favicon.svg differs from the brand mark"

    tokens = json.loads((brand / "tokens.json").read_text())
    assert (branded_email.NAVY, branded_email.INK, branded_email.BRASS,
            branded_email.BRASS_LIGHT, branded_email.MUTED, branded_email.LINE,
            branded_email.SLATE, branded_email.MIST) == (
        tokens["navy"], tokens["ink"], tokens["brass"], tokens["brassLight"], tokens["muted"],
        tokens["line"], tokens["slate"], tokens["mist"])
    assert (receipts.NAVY, receipts.INK, receipts.BRASS, receipts.BRASS_LIGHT) == (
        tokens["navy"], tokens["ink"], tokens["brass"], tokens["brassLight"])
    website = (root / "frontend" / "website" / "src" / "theme.ts").read_text()
    dashboard = (root / "frontend" / "dashboard" / "src" / "theme.ts").read_text()
    checkout = (root / "frontend" / "checkout" / "src" / "styles.css").read_text()
    for name in ("navy", "ink", "brass", "brassLight", "slate", "mist", "line", "muted",
                 "allow", "verify", "block"):
        assert tokens[name] in website, f"website theme lacks {name} {tokens[name]}"
    for name in ("navy", "ink", "brass", "slate"):
        assert tokens[name] in dashboard and tokens[name] in checkout, name
    # The wordmark: lowercase name and a brass full stop, the same in every app.
    for path in ("frontend/checkout/src/Brand.tsx", "frontend/website/src/components/Logo.tsx",
                 "frontend/dashboard/src/components/Wordmark.tsx"):
        source = (root / path).read_text()
        assert ">securepay<" in source and "." in source, f"{path} lacks the wordmark"


def test_email_headline_preview_total_and_button_label():
    """Demo sprint 14: a one-sentence opening is the headline and the inbox preview; the
    item table's Total row stands out; buttons say what the link does."""
    from apps.common.branded_email import button_label, html_for

    body = ("Thank you. Your payment to Volt & Co. was approved.\n\n"
            "Items:\n  Cable x 1  S$19.00\n  Total  S$19.00\n\n"
            "https://gateway.example/guest/status?ref=SP-ABCD-1234\n")
    html = html_for("Receipt", body)
    assert 'font-size:20px' in html and "Thank you. Your payment to Volt &amp; Co." in html
    assert 'display:none' in html  # preview text
    assert "font-weight:700;border-top" in html  # Total row
    assert ">Check payment status</a>" in html
    # A greeting is not a headline.
    assert "font-size:20px" not in html_for("Notice", "Hello,\n\nYour account was locked.\n")
    assert button_label("https://x.example/account/reset#token=abc") == "Choose a new password"
    assert button_label("https://x.example/dashboard/register/verify#token=a") == \
        "Confirm your email"
    assert button_label("https://x.example/somewhere") == "Open the page"


# --- /healthz and /readyz (uptime monitor) -------------------------------------------------

@pytest.mark.django_db(databases=["default", "vault"])
def test_readyz_needs_a_live_worker(client):
    from datetime import timedelta

    from django.utils import timezone

    from apps.events.models import WorkerHeartbeat

    assert client.get("/healthz").json() == {"status": "ok"}
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "problems": ["worker"]}
    assert response["Cache-Control"] == "no-store"

    beat = WorkerHeartbeat.objects.create(name="worker", seen_at=timezone.now())
    response = client.get("/readyz")
    assert response.status_code == 200 and response.json() == {"status": "ok"}

    beat.seen_at -= timedelta(minutes=3)
    beat.save()
    assert client.get("/readyz").status_code == 503


@pytest.mark.parametrize(("hops", "expected"), [(0, "203.0.113.9"), (1, "198.51.100.7")])
def test_rate_limits_count_the_same_client_address_as_screening(settings, hops, expected):
    """DRF's per-IP throttles must not key on the part of X-Forwarded-For a client writes:
    a new made-up address per request would otherwise get a fresh limit every time."""
    from rest_framework.test import APIRequestFactory
    from rest_framework.throttling import AnonRateThrottle

    from apps.common.clientip import client_ip

    settings.TRUSTED_PROXY_HOPS = hops
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": hops}
    request = APIRequestFactory().get("/", HTTP_X_FORWARDED_FOR="10.6.6.6, 198.51.100.7",
                                      REMOTE_ADDR="203.0.113.9")
    assert AnonRateThrottle().get_ident(request) == expected == client_ip(request)


def test_throttle_proxy_count_follows_trusted_proxy_hops():
    from django.conf import settings

    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == settings.TRUSTED_PROXY_HOPS
