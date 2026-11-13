from django.contrib import admin

from apps.checkout.models import VerificationChallenge


@admin.register(VerificationChallenge)
class VerificationChallengeAdmin(admin.ModelAdmin):
    list_display = ("payment", "codes_sent", "wrong_attempts", "code_expires_at", "verified_at")
    exclude = ("code_hash",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
