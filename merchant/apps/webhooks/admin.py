from django.contrib import admin

from apps.webhooks.models import ReceivedEvent


@admin.register(ReceivedEvent)
class ReceivedEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "type", "payment_id", "sequence", "outcome", "received_at")
    list_filter = ("type", "outcome")
    search_fields = ("event_id", "payment_id")
