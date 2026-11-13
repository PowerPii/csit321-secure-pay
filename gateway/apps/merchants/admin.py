from django.contrib import admin

from apps.merchants.models import ApiKey, Merchant


class ApiKeyInline(admin.TabularInline):
    model = ApiKey
    extra = 0
    can_delete = False
    fields = ("public_id", "hint", "created_at", "last_used_at", "revoked_at")
    readonly_fields = ("public_id", "hint", "created_at", "last_used_at")

    def has_add_permission(self, request, obj=None):
        return False  # keys are issued with `manage.py create_merchant` so they are shown once


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("name", "public_id", "status", "webhook_url_approved", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "public_id")
    readonly_fields = ("public_id", "created_at", "updated_at")
    inlines = [ApiKeyInline]
