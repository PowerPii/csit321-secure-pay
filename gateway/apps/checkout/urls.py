"""Hosted checkout API, used only by frontend/checkout. Session-bound; the browser never sets amount."""
from django.urls import path

from apps.common.views import todo

urlpatterns = [
    path("<str:session_id>", todo("order summary for screen C3 (merchant, amount, expiry)"),
         name="checkout-session"),
    path("<str:session_id>/card", todo("send card to vault -> token, brand, last4, fingerprint"),
         name="checkout-card"),
    path("<str:session_id>/submit", todo("screen, then authorise with the simulator (C4)"),
         name="checkout-submit"),
    path("<str:session_id>/verify", todo("check verification code (C5)"), name="checkout-verify"),
    path("<str:session_id>/verify/resend", todo("send a new verification code"),
         name="checkout-verify-resend"),
    path("<str:session_id>/result", todo("result for C6/C7"), name="checkout-result"),
    path("status/<str:token>", todo("guest read-only status link (C9)"), name="guest-status"),
]
