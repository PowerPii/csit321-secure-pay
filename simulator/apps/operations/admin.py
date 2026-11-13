from django.contrib import admin

from apps.operations.models import Authorisation, OperationRecord


@admin.register(OperationRecord)
class OperationRecordAdmin(admin.ModelAdmin):
    list_display = ("operation_id", "type", "status", "decline_reason", "amount", "recorded_at")
    list_filter = ("type", "status")
    search_fields = ("operation_id", "payment_id", "simulator_reference")


@admin.register(Authorisation)
class AuthorisationAdmin(admin.ModelAdmin):
    list_display = ("operation_id", "state", "authorised_amount", "captured_amount",
                    "refunded_amount")
