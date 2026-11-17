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
    assert Product.objects.count() == 12
    r = client.get("/")
    assert b"Wireless mouse" in r.content and b"S$ 29.90" in r.content
    assert b"Volt Book 14" in r.content and b"test mode" in r.content


def test_category_filter_and_product_page(client):
    r = client.get("/category/audio")
    assert b"Volt Quiet Over-ear Headphones" in r.content and b"Wireless mouse" not in r.content
    assert client.get("/?category=audio")["Location"] == "/category/audio"  # old links
    assert b"Wireless mouse" in client.get("/?category=nope").content  # unknown: home
    assert client.get("/category/nope").status_code == 404
    r = client.get("/products/HEAD-01")
    assert r.status_code == 200 and b"S$ 249.00" in r.content and b"40 hours" in r.content
    assert client.get("/products/NOPE").status_code == 404


def test_help_pages(client):
    for page in ("delivery", "returns", "about"):
        assert client.get(f"/help/{page}").status_code == 200
    assert client.get("/help/nope").status_code == 404


def test_cart_prices_come_from_the_database(client):
    add(client, "MOUSE-01", "MOUSE-01", "NOPE")
    assert b"Cart (2)" in client.get("/").content
    r = client.get("/cart")
    assert b"S$ 59.80" in r.content and b"S$ 4.90" in r.content and b"S$ 64.70" in r.content
    client.post("/cart/remove", {"sku": "MOUSE-01"})
    assert b"Cart (0)" in client.get("/").content


def test_small_orders_pay_for_delivery_as_a_line_item(client, gateway):
    add(client, "CABLE-01")
    client.post("/checkout", {"email": "alex@example.com", "full_name": "Alex Tan",
                              "delivery_address": "Blk 123 Clementi Ave 3"})
    order = Order.objects.get()
    assert order.total_cents == 1900 + 490
    body = gateway.calls[0][2]
    assert body["amount"] == 2390
    assert body["line_items"][-1] == {"name": "Standard delivery", "quantity": 1,
                                      "unit_amount": 490}
    assert sum(i["unit_amount"] * i["quantity"] for i in body["line_items"]) == body["amount"]


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


# Sprint 13: the store looks and behaves like a real one.

def test_categories_sort_by_price(client):
    page = client.get("/category/computing?sort=price").content.decode()
    assert page.index("Laptop stand") < page.index("Volt Book 14")
    page = client.get("/category/computing?sort=price-desc").content.decode()
    assert page.index("Volt Book 14") < page.index("Laptop stand")
    assert client.get("/category/computing?sort=evil").status_code == 200  # ignored


def test_search_finds_products_by_name_and_words(client):
    assert b"Volt Go Speaker" in client.get("/search?q=waterproof").content
    page = client.get("/search?q=CHARGER").content
    assert b"Volt 65W GaN Charger" in page and b"Wireless mouse" not in page
    assert b"Nothing matches" in client.get("/search?q=zzzz").content
    assert b"Type what you are looking for" in client.get("/search").content
    assert client.get("/search?q=" + "x" * 500).status_code == 200


def test_home_has_category_tiles(client):
    page = client.get("/").content
    for slug in (b"/category/audio", b"/category/computing", b"/category/accessories"):
        assert slug in page


def test_cart_quantity_can_change(client):
    add(client, "MOUSE-01")
    client.post("/cart/update", {"sku": "MOUSE-01", "quantity": "3"})
    assert b"Cart (3)" in client.get("/").content
    client.post("/cart/update", {"sku": "MOUSE-01", "quantity": "99"})
    assert b"Cart (10)" in client.get("/").content  # at most 10 of a thing
    client.post("/cart/update", {"sku": "MOUSE-01", "quantity": "abc"})
    assert b"Cart (10)" in client.get("/").content
    client.post("/cart/update", {"sku": "HUB-01", "quantity": "2"})  # not in the cart
    client.post("/cart/update", {"sku": "MOUSE-01", "quantity": "0"})
    assert b"Cart (0)" in client.get("/").content


def test_stock_is_shown_and_limits_the_cart(client):
    Product.objects.filter(sku="HEAD-01").update(stock=2)
    Product.objects.filter(sku="SPK-01").update(stock=0)
    assert b"Only 2 left" in client.get("/products/HEAD-01").content
    assert b"Sold out" in client.get("/products/SPK-01").content
    assert b"Sold out" in client.get("/category/audio").content
    r = client.post("/cart/add", {"sku": "SPK-01"})
    assert r["Location"] == "/products/SPK-01"
    assert b"is sold out" in client.get(r["Location"]).content
    add(client, "HEAD-01", "HEAD-01", "HEAD-01")
    page = client.get("/cart").content
    assert b"Cart (2)" in page and b"all in your cart" in page
    client.post("/cart/update", {"sku": "HEAD-01", "quantity": "5"})
    assert b"Cart (2)" in client.get("/").content


def test_checkout_stops_when_stock_ran_out_meanwhile(client, gateway):
    add(client, "MOUSE-01")
    Product.objects.filter(sku="MOUSE-01").update(stock=0)
    r = client.post("/checkout", {"email": "alex@example.com", "full_name": "Alex Tan",
                                  "delivery_address": "Blk 123 Clementi Ave 3"})
    assert r["Location"] == "/cart" and not Order.objects.exists() and gateway.calls == []
    assert b"Not enough stock" in client.get("/cart").content


def test_paid_orders_take_stock_once(client, gateway):
    before = {p.sku: p.stock for p in Product.objects.filter(sku__in=["MOUSE-01", "HUB-01"])}
    place_order(client)
    order = Order.objects.get()
    assert Product.objects.get(sku="MOUSE-01").stock == before["MOUSE-01"]  # not paid yet
    for _ in range(2):  # the return and the order page both confirm the payment
        client.get(f"/orders/{order.number}/return?payment_id={order.latest_attempt.payment_id}")
        client.get(f"/orders/{order.number}")
    assert Product.objects.get(sku="MOUSE-01").stock == before["MOUSE-01"] - 1
    assert Product.objects.get(sku="HUB-01").stock == before["HUB-01"] - 1


def test_stock_never_goes_below_zero(client, gateway):
    place_order(client)
    Product.objects.filter(sku="MOUSE-01").update(stock=0)
    order = Order.objects.get()
    client.get(f"/orders/{order.number}")
    assert Product.objects.get(sku="MOUSE-01").stock == 0


def test_restock_command():
    from django.core.management import call_command
    from django.core.management.base import CommandError

    call_command("restock", "--to", "3")
    assert set(Product.objects.values_list("stock", flat=True)) == {3}
    call_command("restock", "--sku", "LAPTOP-14", "--to", "0")
    assert Product.objects.get(sku="LAPTOP-14").stock == 0
    with pytest.raises(CommandError):
        call_command("restock", "--sku", "NOPE")
    with pytest.raises(CommandError):
        call_command("restock", "--to", "-1")


def test_confirmation_page_shows_delivery_and_progress(client, gateway):
    place_order(client)
    order = Order.objects.get()
    page = client.get(f"/orders/{order.number}").content.decode()
    assert "Thanks, Alex Tan!" in page and "Delivering to" in page
    assert "Blk 123 Clementi Ave 3" in page and "alex@example.com" in page
    assert "Arrives " in page and "Includes GST" in page


def test_my_orders_lists_status_and_items(client, gateway):
    gateway.next_status = "declined"
    place_order(client)
    page = client.get("/orders").content.decode()
    assert "Wireless mouse and 1 more" in page and "Awaiting payment" in page
    client.get(f"/orders/{Order.objects.get().number}")  # learns about the decline
    assert "Payment not completed" in client.get("/orders").content.decode()


@pytest.mark.parametrize("paid_at, arrives", [
    ("2026-12-07T09:00:00+08:00", "2026-12-08"),  # Monday morning: arrives Tuesday
    ("2026-12-07T15:00:00+08:00", "2026-12-09"),  # Monday after 2 pm: ships Tuesday
    ("2026-12-12T10:00:00+08:00", "2026-12-14"),  # Saturday: no Sunday delivery
    ("2026-12-05T01:00:00+00:00", "2026-12-07"),  # Sat 9 am SGT, given in UTC
])
def test_estimated_delivery(paid_at, arrives):
    import datetime

    from apps.shop.catalogue import estimated_delivery

    when = datetime.datetime.fromisoformat(paid_at)
    assert estimated_delivery(when) == datetime.date.fromisoformat(arrives)


def test_missing_pages_use_the_store_look(client, settings):
    settings.DEBUG = False
    r = client.get("/no-such-page")
    assert r.status_code == 404 and b"find that page" in r.content and b"Volt" in r.content


@pytest.mark.django_db
def test_healthz_checks_the_database(client):
    response = client.get("/healthz")
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    assert "no-cache" in response["Cache-Control"]
