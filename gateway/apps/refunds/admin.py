from django.contrib import admin

from apps.refunds.models import Refund


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    """Read-only: refunds are created through the API so the reservation rule holds."""

    list_display = ("reference", "public_id", "payment", "amount", "status", "failure_reason",
                    "created_at")
    list_filter = ("status",)
    search_fields = ("reference", "public_id", "payment__reference", "payment__public_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
