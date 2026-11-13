"""Merchant API (authenticated by API key). Every state-changing call needs an Idempotency-Key."""
from django.urls import path

from apps.common.views import todo
from apps.payments.views import PaymentDetailView, PaymentListView

urlpatterns = [
    path("payments", PaymentListView.as_view(), name="payment-list"),
    path("payments/<str:payment_id>", PaymentDetailView.as_view(), name="payment-detail"),
    path("payments/<str:payment_id>/capture", todo("capture an authorised payment"),
         name="payment-capture"),
    path("payments/<str:payment_id>/cancel", todo("void an authorised payment"),
         name="payment-cancel"),
]
