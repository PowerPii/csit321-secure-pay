"""Demo shop: cart, order summary, starting a SecurePay payment and confirming it (sprint 2)."""
import pytest

from apps.shop.models import Order, PaymentAttempt, Product
from apps.shop.templatetags.shop import money

pytestmark = pytest.mark.django_db


def add(client, *skus):
    for sku in skus:
        client.post("/cart/add", {"sku": sku})


def place_order(client):
    add(client, "MOUSE-01", "HUB-01")
    return client.post("/checkout", {"email": "alex@example.com", "full_name": "Alex Tan",
                                     "delivery_address": "Blk 123 Clementi Ave 3"})


def test_money_filter():
    assert money(8990) == "S$ 89.90" and money(1000000) == "S$ 10,000.00"


def test_products_are_seeded_and_listed(client):
    assert Product.objects.count() == 4
    r = client.get("/")
    assert b"Wireless mouse" in r.content and b"S$ 29.90" in r.content


def test_cart_prices_come_from_the_database(client):
    add(client, "MOUSE-01", "MOUSE-01", "NOPE")
    r = client.get("/")
    assert b"Cart (2)" in r.content and b"S$ 59.80" in r.content
    client.post("/cart/remove", {"sku": "MOUSE-01"})
    assert b"Cart (0)" in client.get("/").content


def test_checkout_needs_a_cart(client):
    assert client.get("/checkout").status_code == 302


def test_checkout_form_validation(client, gateway):
    add(client, "MOUSE-01")
    r = client.post("/checkout", {"email": "nope", "full_name": "", "delivery_address": ""})
    assert r.status_code == 200 and not Order.objects.exists() and gateway.calls == []


def test_placing_an_order_creates_a_payment_and_redirects_to_checkout(client, gateway):
    r = place_order(client)
    order = Order.objects.get()
    assert order.total_cents == 8990
    [(method, path, body, headers)] = gateway.calls
    assert (method, path) == ("POST", "/v1/payments")
    assert body == {"amount": 8990, "currency": "SGD", "order_reference": order.reference,
                    "return_url": f"https://shop.localhost/orders/{order.number}/return",
                    "customer_email": "alex@example.com",
                    "description": "Wireless mouse × 1, USB-C hub × 1",
                    "line_items": [
                        {"name": "Wireless mouse", "quantity": 1, "unit_amount": 2990},
                        {"name": "USB-C hub", "quantity": 1, "unit_amount": 6000}]}
    attempt = order.latest_attempt
    assert headers["idempotency-key"] == str(attempt.idempotency_key)
    assert r.status_code == 302 and r["Location"] == attempt.checkout_url
    assert attempt.payment_id.startswith("pay_") and attempt.status == "created"
    assert b"Cart (0)" in client.get("/").content


def test_return_marks_paid_only_after_signed_confirmation(client, gateway):
    place_order(client)
    order = Order.objects.get()
    attempt = order.latest_attempt
    r = client.get(f"/orders/{order.number}/return?payment_id={attempt.payment_id}")
    assert r.status_code == 302
    order.refresh_from_db()
    assert order.paid_at is not None
    page = client.get(f"/orders/{order.number}")
    attempt.refresh_from_db()
    assert b"Payment confirmed" in page.content and attempt.reference.encode() in page.content
    assert gateway.calls[-1][:2] == ("GET", f"/v1/payments/{attempt.payment_id}")


@pytest.mark.parametrize("mode", ["unsigned", "bad_signature"])
def test_untrusted_reply_never_marks_paid(client, gateway, mode):
    place_order(client)
    order = Order.objects.get()
    gateway.mode = mode
    client.get(f"/orders/{order.number}/return?payment_id={order.latest_attempt.payment_id}")
    order.refresh_from_db()
    assert order.paid_at is None


def test_reply_for_another_amount_never_marks_paid(client, gateway):
    place_order(client)
    order = Order.objects.get()
    gateway.amount_override = 50
    client.get(f"/orders/{order.number}")
    order.refresh_from_db()
    assert order.paid_at is None


def test_waiting_page_refreshes_itself(client, gateway):
    place_order(client)
    order = Order.objects.get()
    gateway.next_status = "unresolved"
    page = client.get(f"/orders/{order.number}")
    assert b"Waiting for payment confirmation" in page.content
    assert b'http-equiv="refresh"' in page.content


def test_verification_required_links_back_to_the_payment_page(client, gateway):
    place_order(client)
    order = Order.objects.get()
    gateway.next_status = "verification_required"
    page = client.get(f"/orders/{order.number}").content.decode()
    assert "emailed you a verification code" in page
    assert "Continue to payment" in page
    assert order.latest_attempt.checkout_url in page


def test_declined_then_try_another_card_makes_a_new_payment(client, gateway):
    place_order(client)
    order = Order.objects.get()
    first = order.latest_attempt
    gateway.next_status = "declined"
    assert b"Try another card" in client.get(f"/orders/{order.number}").content
    r = client.post(f"/orders/{order.number}/pay")
    second = order.latest_attempt
    assert second.pk != first.pk and second.idempotency_key != first.idempotency_key
    assert second.payment_id != first.payment_id
    assert r["Location"] == second.checkout_url


def test_gateway_down_then_retry_reuses_the_idempotency_key(client, gateway):
    gateway.mode = "down"
    r = place_order(client)
    order = Order.objects.get()
    assert r["Location"] == f"/orders/{order.number}"
    assert b"couldn&#x27;t start the payment" in client.get(r["Location"]).content
    key = order.latest_attempt.idempotency_key
    gateway.mode = "normal"
    r = client.post(f"/orders/{order.number}/pay")
    assert PaymentAttempt.objects.count() == 1
    assert order.latest_attempt.idempotency_key == key and order.latest_attempt.payment_id
    assert r.status_code == 302 and r["Location"].startswith("https://gateway.localhost/pay/")


def test_unfinished_checkout_can_be_continued(client, gateway):
    place_order(client)
    order = Order.objects.get()
    gateway.next_status = "created"
    page = client.get(f"/orders/{order.number}")
    assert b"Awaiting payment" in page.content


def test_orders_are_private_to_the_browser_that_placed_them(client, gateway):
    from django.test import Client

    place_order(client)
    order = Order.objects.get()
    stranger = Client()
    assert stranger.get(f"/orders/{order.number}").status_code == 404
    assert stranger.get(f"/orders/{order.number}/return?payment_id=x").status_code == 404
    assert stranger.post(f"/orders/{order.number}/pay").status_code == 404
    assert b"Order #" in client.get("/orders").content
