from django.contrib import admin

from apps.customers.models import CustomerAccount


@admin.register(CustomerAccount)
class CustomerAccountAdmin(admin.ModelAdmin):
    list_display = ("public_id", "email", "full_name", "is_active", "locked_until", "created_at")
    search_fields = ("email", "public_id")
    exclude = ("password",)
    readonly_fields = ("public_id", "email", "failed_attempts", "last_sign_in_at",
                       "password_changed_at", "created_at")
