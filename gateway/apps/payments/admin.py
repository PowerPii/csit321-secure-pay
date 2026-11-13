from django.contrib import admin

from apps.payments.models import IdempotencyRecord, Operation, Payment


class OperationInline(admin.TabularInline):
    model = Operation
    extra = 0
    can_delete = False
    readonly_fields = ("public_id", "type", "status", "amount", "reconciliation_checks",
                       "created_at", "completed_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Read-only: payment state changes go through the API so they are audited."""

    list_display = ("reference", "public_id", "merchant", "status", "amount", "created_at")
    list_filter = ("status",)
    search_fields = ("reference", "public_id", "order_reference")
    inlines = [OperationInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ("key", "merchant", "method", "path", "status", "response_status", "expires_at")
    exclude = ("response_body",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
