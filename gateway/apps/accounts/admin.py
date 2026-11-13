from django.contrib import admin, messages

from apps.accounts.models import StaffAccount
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit


@admin.register(StaffAccount)
class StaffAccountAdmin(admin.ModelAdmin):
    """Read-only list of dashboard accounts. New accounts: `manage.py create_staff`."""

    list_display = ("public_id", "user", "role", "merchant", "failed_attempts", "locked_until",
                    "last_sign_in_at")
    list_filter = ("role",)
    search_fields = ("public_id", "user__email")
    readonly_fields = ("public_id", "user", "role", "merchant", "failed_attempts",
                       "locked_until", "last_sign_in_at", "created_at")
    actions = ["unlock"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Unlock (clear failed sign-ins)")
    def unlock(self, request, queryset):
        for account in queryset:
            StaffAccount.objects.filter(pk=account.pk).update(failed_attempts=0,
                                                              locked_until=None)
            audit("staff.unlocked", actor_type=AuditEvent.ActorType.STAFF,
                  actor_id=request.user.get_username(), target_type="staff",
                  target_id=account.public_id)
        self.message_user(request, f"Unlocked {queryset.count()} account(s).", messages.SUCCESS)
