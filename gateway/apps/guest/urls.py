"""Guest status check (API-CONTRACT.md section 8), served under /guest/status/."""
from django.urls import path

from apps.guest import views

urlpatterns = [
    path("code", views.CodeView.as_view(), name="guest-status-code"),
    path("verify", views.VerifyView.as_view(), name="guest-status-verify"),
    path("payment", views.PaymentView.as_view(), name="guest-status-payment"),
    path("receipt.pdf", views.ReceiptView.as_view(), name="guest-status-receipt"),
    path("sign-out", views.SignOutView.as_view(), name="guest-status-sign-out"),
]
