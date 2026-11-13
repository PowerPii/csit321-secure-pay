from django.contrib import admin

from apps.guest.models import StatusChallenge, StatusLock


@admin.register(StatusChallenge)
class StatusChallengeAdmin(admin.ModelAdmin):
    list_display = ("public_id", "payment", "expires_at", "replaced_at", "used_at",
                    "created_at")
    readonly_fields = ("public_id", "pair_key", "ip_key", "payment", "code_hash", "expires_at",
                       "replaced_at", "used_at", "created_at")


@admin.register(StatusLock)
class StatusLockAdmin(admin.ModelAdmin):
    list_display = ("pair_key", "wrong_attempts", "locked_until", "updated_at")
