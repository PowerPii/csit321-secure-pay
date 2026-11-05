"""Merchant API (authenticated by API key). Every state-changing call needs an Idempotency-Key."""
from django.urls import path

from apps.common.views import todo

urlpatterns = [
    path("payments", todo("create payment (amount, currency, order ref) -> id + checkout URL"),
         name="payment-list"),
    path("payments/<str:payment_id>", todo("get payment status for the calling merchant only"),
         name="payment-detail"),
    path("payments/<str:payment_id>/capture", todo("capture an authorised payment"),
         name="payment-capture"),
    path("payments/<str:payment_id>/cancel", todo("void an authorised payment"),
         name="payment-cancel"),
]
