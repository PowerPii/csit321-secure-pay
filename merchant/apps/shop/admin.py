"""Shop back office (Django admin): orders, and capture or cancel of their payments (S1)."""
from django.contrib import admin, messages

from apps.shop import payments, securepay
from apps.shop.models import Order, OrderLine, PaymentAttempt, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "price_cents", "position")


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    readonly_fields = ("sku", "name", "unit_price_cents", "quantity")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "email", "total_cents", "paid_at", "created_at")
    inlines = (OrderLineInline,)


def _settle(modeladmin, request, queryset, action):
    for attempt in queryset.select_related("order"):
        if not attempt.payment_id:
            continue
        try:
            status = action(attempt)
        except (payments.SettleError, securepay.GatewayError) as exc:
            modeladmin.message_user(request, f"{attempt.order.reference}: {exc}",
                                    messages.ERROR)
            continue
        modeladmin.message_user(request, f"{attempt.order.reference}: {status}")


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ("order", "payment_id", "reference", "status", "captured_amount",
                    "sequence", "updated_at")
    list_filter = ("status",)
    search_fields = ("payment_id", "reference")
    readonly_fields = ("order", "payment_id", "reference", "status", "sequence",
                       "checkout_url", "captured_amount")
    actions = ("capture", "cancel")

    @admin.action(description="Capture the full amount (ship the order)")
    def capture(self, request, queryset):
        _settle(self, request, queryset, payments.capture)

    @admin.action(description="Cancel the authorisation (nothing is charged)")
    def cancel(self, request, queryset):
        _settle(self, request, queryset, payments.cancel)
