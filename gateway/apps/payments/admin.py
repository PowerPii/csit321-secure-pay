from django.contrib import admin, messages

from apps.audit.models import AuditEvent
from apps.payments import reconciliation
from apps.payments.models import IdempotencyRecord, Operation, Payment


class OperationInline(admin.TabularInline):
    model = Operation
    extra = 0
    can_delete = False
    readonly_fields = ("public_id", "type", "status", "amount", "reconciliation_checks",
                       "next_check_at", "escalated_at", "created_at", "completed_at")
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


class EscalatedFilter(admin.SimpleListFilter):
    title = "escalated"
    parameter_name = "escalated"

    def lookups(self, request, model_admin):
        return [("yes", "Escalated, still unresolved")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(status=Operation.Status.UNRESOLVED,
                                   escalated_at__isnull=False)
        return queryset


@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    """Unresolved and escalated operations (UC-42); the dashboard has the same view. Read-only:
    the only action is a re-check with the simulator (FR-TXN-13); nobody sets an outcome."""

    list_display = ("public_id", "type", "status", "payment", "amount",
                    "reconciliation_checks", "next_check_at", "escalated_at", "created_at")
    list_filter = ("status", "type", EscalatedFilter)
    search_fields = ("public_id", "payment__public_id", "payment__reference")
    exclude = ("evidence_body", "evidence_signature")
    actions = ["recheck"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Re-check with the simulator (status query, same operation ID)")
    def recheck(self, request, queryset):
        actor = (AuditEvent.ActorType.STAFF, request.user.get_username())
        for operation in queryset.filter(status=Operation.Status.UNRESOLVED):
            result = reconciliation.check(operation.pk, actor=actor, manual=True)
            level = messages.SUCCESS if result.status != Operation.Status.UNRESOLVED \
                else messages.WARNING
            self.message_user(request, f"{result.public_id}: {result.status}", level)
