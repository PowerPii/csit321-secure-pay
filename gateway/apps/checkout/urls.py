"""Hosted checkout API, used only by frontend/checkout. Session-bound; the browser never sets amount."""
from django.urls import path

from apps.checkout import views
from apps.common.views import todo

urlpatterns = [
    path("<str:session_id>", views.SessionView.as_view(), name="checkout-session"),
    path("<str:session_id>/card", views.CardView.as_view(), name="checkout-card"),
    path("<str:session_id>/submit", views.SubmitView.as_view(), name="checkout-submit"),
    path("<str:session_id>/verify", todo("check verification code (C5, sprint 4)"),
         name="checkout-verify"),
    path("<str:session_id>/verify/resend", todo("send a new verification code (sprint 4)"),
         name="checkout-verify-resend"),
    path("<str:session_id>/result", views.ResultView.as_view(), name="checkout-result"),
    path("status/<str:token>", todo("guest status, replaced by /guest/status (contract 8)"),
         name="guest-status"),
]
