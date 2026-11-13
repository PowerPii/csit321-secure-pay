"""Merchant API (authenticated by API key). Every state-changing call needs an Idempotency-Key."""
from django.urls import path

from apps.payments.views import (
    PaymentCancelView,
    PaymentCaptureView,
    PaymentDetailView,
    PaymentListView,
)

urlpatterns = [
    path("payments", PaymentListView.as_view(), name="payment-list"),
    path("payments/<str:payment_id>", PaymentDetailView.as_view(), name="payment-detail"),
    path("payments/<str:payment_id>/capture", PaymentCaptureView.as_view(),
         name="payment-capture"),
    path("payments/<str:payment_id>/cancel", PaymentCancelView.as_view(),
         name="payment-cancel"),
]
