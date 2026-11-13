from django.contrib import admin

from apps.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "action", "actor_type", "actor_id", "merchant_id", "target_id")
    list_filter = ("action", "actor_type")
    search_fields = ("target_id", "request_id", "merchant_id", "actor_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
