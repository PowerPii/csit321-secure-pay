from django.contrib import admin

from apps.faults.models import FaultRule


@admin.register(FaultRule)
class FaultRuleAdmin(admin.ModelAdmin):
    list_display = ("public_id", "action", "match", "delay_ms", "copies", "remaining",
                    "created_at")
