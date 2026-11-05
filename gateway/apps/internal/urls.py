"""Staff API for frontend/dashboard. Session auth + TOTP; every view scopes by role and merchant."""
from django.urls import path

from apps.common.views import todo

urlpatterns = [
    path("auth/login", todo("D1 password sign-in, django-axes lockout"), name="staff-login"),
    path("auth/totp", todo("D2 TOTP check / first-time setup"), name="staff-totp"),
    path("auth/logout", todo("end session"), name="staff-logout"),
    path("me", todo("current user, role and merchant"), name="staff-me"),
    path("payments", todo("D3 list, filter by status/date; merchant-scoped"),
         name="staff-payments"),
    path("payments/<str:payment_id>", todo("D4 detail + fraud decision + timeline"),
         name="staff-payment-detail"),
    path("payments/<str:payment_id>/refunds", todo("D5 refund from the dashboard"),
         name="staff-refund"),
    path("payments/<str:payment_id>/capture", todo("capture from the dashboard"),
         name="staff-capture"),
    path("payments/<str:payment_id>/cancel", todo("void from the dashboard"),
         name="staff-cancel"),
    path("reviews", todo("D6 fraud review queue, sort/filter by score"), name="review-list"),
    path("reviews/<str:case_id>", todo("D6b case detail, findings, review status"),
         name="review-detail"),
    path("merchants", todo("admin: list/create/approve merchants"), name="merchant-admin"),
    path("audit", todo("admin: read-only audit log"), name="audit-list"),
]
