"""Read-only analyst view of screening decisions until the dashboard (D4, D6) lands in
sprint 6: outcome, score, reasons, feature values and the model / rules / policy versions."""
from django.contrib import admin

from apps.risk.models import RiskListEntry, ScreeningEvent


@admin.register(ScreeningEvent)
class ScreeningEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "payment_reference", "outcome", "score", "reason_list",
                    "model_version", "elapsed_ms")
    list_filter = ("outcome", "model_version", "policy_version")
    search_fields = ("public_id", "payment__reference", "payment__public_id")
    fields = ("public_id", "payment", "merchant", "occurred_at", "amount", "outcome", "score",
              "reasons", "features", "model_version", "rules_version", "policy_version",
              "feature_schema_version", "elapsed_ms", "error")
    readonly_fields = fields

    @admin.display(description="Payment")
    def payment_reference(self, obj):
        return obj.payment.reference

    @admin.display(description="Reasons")
    def reason_list(self, obj):
        return ", ".join(obj.reasons) or "-"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RiskListEntry)
class RiskListEntryAdmin(admin.ModelAdmin):
    list_display = ("kind", "action", "label", "active", "created_at")
    list_filter = ("kind", "action", "active")
    readonly_fields = ("kind", "value_hash", "created_at")
