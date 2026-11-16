"""Storefront pages of Volt & Co., the demo merchant (wireframes C1, C2 and C8, dressed up).

The store is fictional: it sells nothing and takes no real money. Payments go through
SecurePay exactly as before.
"""
from django import forms
from django.contrib import messages
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.shop import catalogue, payments, securepay
from apps.shop.models import Order, OrderLine, PaymentAttempt, Product

MAX_QUANTITY = 10
SESSION_CART = "cart"
SESSION_ORDERS = "orders"


class DeliveryForm(forms.Form):
    email = forms.EmailField(max_length=254, widget=forms.EmailInput(
        attrs={"placeholder": "you@example.com", "autocomplete": "email"}))
    full_name = forms.CharField(max_length=120, widget=forms.TextInput(
        attrs={"placeholder": "Tan Wei Ming", "autocomplete": "name"}))
    delivery_address = forms.CharField(max_length=300, widget=forms.TextInput(
        attrs={"placeholder": "Blk 123 Clementi Ave 3, #05-67",
               "autocomplete": "street-address"}))


def _cart(request) -> dict[str, int]:
    return dict(request.session.get(SESSION_CART, {}))


def _cart_lines(request):
    """Prices always come from the database, never from the browser."""
    cart = _cart(request)
    products = {p.sku: p for p in Product.objects.filter(sku__in=cart)}
    lines = [(products[sku], qty) for sku, qty in cart.items() if sku in products]
    lines = [{"product": p, "quantity": q, "total_cents": p.price_cents * q} for p, q in lines]
    return lines, sum(line["total_cents"] for line in lines)


def _totals(subtotal: int) -> dict:
    shipping = catalogue.shipping_cents(subtotal)
    return {"subtotal_cents": subtotal, "shipping_cents": shipping,
            "total_cents": subtotal + shipping,
            "free_shipping_gap_cents": max(catalogue.FREE_SHIPPING_FROM_CENTS - subtotal, 0)}


def _cart_count(request) -> int:
    return sum(_cart(request).values())


def _owned_order(request, number: int) -> Order:
    """Orders are visible only to the browser session that placed them."""
    if number not in request.session.get(SESSION_ORDERS, []):
        raise Http404
    order = Order.objects.filter(pk=number - 1000).prefetch_related("lines").first()
    if order is None:
        raise Http404
    return order


@require_GET
def home(request):
    categories = dict(Product.CATEGORIES)
    category = request.GET.get("category", "")
    products = Product.objects.all()
    if category in categories:
        products = products.filter(category=category)
    else:
        category = ""
    return render(request, "shop/home.html", {
        "products": products, "categories": Product.CATEGORIES, "category": category,
        "category_name": categories.get(category, "All products"),
        "hero": Product.objects.filter(sku="LAPTOP-14").first(),
        "cart_count": _cart_count(request)})


@require_GET
def product_detail(request, sku: str):
    product = Product.objects.filter(sku=sku).first()
    if product is None:
        raise Http404
    related = Product.objects.filter(category=product.category).exclude(pk=product.pk)[:3]
    return render(request, "shop/product.html", {
        "product": product, "related": related, "cart_count": _cart_count(request),
        "free_shipping_from_cents": catalogue.FREE_SHIPPING_FROM_CENTS})


@require_GET
def cart_view(request):
    lines, subtotal = _cart_lines(request)
    return render(request, "shop/cart.html", {
        "lines": lines, **_totals(subtotal), "cart_count": _cart_count(request)})


@require_POST
def cart_add(request):
    sku = request.POST.get("sku", "")
    if Product.objects.filter(sku=sku).exists():
        cart = _cart(request)
        cart[sku] = min(cart.get(sku, 0) + 1, MAX_QUANTITY)
        request.session[SESSION_CART] = cart
    return redirect("shop-cart")


@require_POST
def cart_remove(request):
    cart = _cart(request)
    cart.pop(request.POST.get("sku", ""), None)
    request.session[SESSION_CART] = cart
    return redirect("shop-cart")


INFO_PAGES = {
    "delivery": "Delivery",
    "returns": "Returns and refunds",
    "about": "About Volt & Co.",
}


@require_GET
def info(request, page: str):
    if page not in INFO_PAGES:
        raise Http404
    return render(request, f"shop/info_{page}.html", {
        "title": INFO_PAGES[page], "cart_count": _cart_count(request),
        "shipping_fee_cents": catalogue.SHIPPING_FEE_CENTS,
        "free_shipping_from_cents": catalogue.FREE_SHIPPING_FROM_CENTS})


@require_http_methods(["GET", "POST"])
def checkout(request):
    lines, subtotal = _cart_lines(request)
    if not lines:
        return redirect("shop-home")
    totals = _totals(subtotal)
    total = totals["total_cents"]
    form = DeliveryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not request.session.session_key:
            request.session.save()
        with transaction.atomic():
            order = Order.objects.create(session_key=request.session.session_key,
                                         total_cents=total, **form.cleaned_data)
            OrderLine.objects.bulk_create([
                OrderLine(order=order, sku=line["product"].sku, name=line["product"].name,
                          unit_price_cents=line["product"].price_cents,
                          quantity=line["quantity"]) for line in lines])
            if totals["shipping_cents"]:
                OrderLine.objects.create(order=order, sku=catalogue.SHIPPING_SKU,
                                         name=catalogue.SHIPPING_NAME, quantity=1,
                                         unit_price_cents=totals["shipping_cents"])
        request.session[SESSION_CART] = {}
        request.session[SESSION_ORDERS] = [*request.session.get(SESSION_ORDERS, []),
                                           order.number]
        return _go_to_checkout(request, order)
    return render(request, "shop/checkout.html", {
        "form": form, "lines": lines, **totals, "cart_count": _cart_count(request)})


def _go_to_checkout(request, order: Order):
    try:
        attempt = payments.start_payment(order)
    except securepay.GatewayError:
        messages.error(request, "We couldn't start the payment with SecurePay. Nothing was "
                                "charged. Please try again in a moment.")
        return redirect("shop-order", number=order.number)
    if not attempt.checkout_url:
        return redirect("shop-order", number=order.number)
    return HttpResponseRedirect(attempt.checkout_url)


@require_POST
def order_pay(request, number: int):
    """Pay again after a decline, an expired checkout or a failed start (C7 "Try another card")."""
    order = _owned_order(request, number)
    attempt = order.latest_attempt
    if order.paid_at:
        return redirect("shop-order", number=order.number)
    if attempt and attempt.payment_id:
        payments.refresh(attempt)
        attempt.refresh_from_db()
        if attempt.status == "created" and attempt.checkout_url:
            return HttpResponseRedirect(attempt.checkout_url)  # still open: continue it
        if attempt.status not in PaymentAttempt.FAILED:
            return redirect("shop-order", number=order.number)  # paid or still deciding
        PaymentAttempt.objects.create(order=order)  # a fresh payment, a fresh key
    return _go_to_checkout(request, order)


@require_GET
def order_return(request, number: int):
    """The customer's browser coming back from SecurePay (return_url?payment_id=...).

    This is navigation only: the order is marked paid only from a signed GET of the payment
    (or a verified webhook, confirmed the same way).
    """
    order = _owned_order(request, number)
    payment_id = request.GET.get("payment_id", "")
    attempt = order.attempts.filter(payment_id=payment_id).first() if payment_id else None
    attempt = attempt or order.latest_attempt
    if attempt is not None:
        payments.refresh(attempt)
    return redirect("shop-order", number=order.number)


@require_GET
def order_detail(request, number: int):
    order = _owned_order(request, number)
    attempt = order.latest_attempt
    if attempt and not order.paid_at and attempt.status not in PaymentAttempt.FAILED:
        payments.refresh(attempt)  # in case the webhook has not arrived yet
        attempt.refresh_from_db()
        order.refresh_from_db()
    if attempt and attempt.status == "cancelled":
        state = "cancelled"  # voided by the shop or expired after 7 days
    elif order.paid_at:
        state = "paid"
    elif attempt is None or not attempt.payment_id:
        state = "not_started"
    elif attempt.status in PaymentAttempt.WAITING:
        state = "waiting"
    elif attempt.status in PaymentAttempt.FAILED:
        state = attempt.status
    else:
        state = "unpaid"  # created: the customer left the checkout page
    return render(request, "shop/order.html", {
        "order": order, "attempt": attempt, "state": state, "lines": order.lines.all(),
        "cart_count": _cart_count(request)})


@require_GET
def order_list(request):
    numbers = request.session.get(SESSION_ORDERS, [])
    orders = Order.objects.filter(pk__in=[n - 1000 for n in numbers])
    return render(request, "shop/orders.html", {"orders": orders,
                                                "cart_count": _cart_count(request)})
