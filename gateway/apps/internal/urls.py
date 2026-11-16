"""Staff API for frontend/dashboard. Session auth + TOTP; every view scopes by role and merchant."""
from django.urls import path

from apps.internal.views import accounts, admin, auth, merchant, payments, reviews
from apps.reconciliation.views import SimulatorNotificationView

urlpatterns = [
    path("auth/login", auth.LoginView.as_view(), name="staff-login"),
    path("auth/totp", auth.TotpView.as_view(), name="staff-totp"),
    path("auth/logout", auth.LogoutView.as_view(), name="staff-logout"),
    path("auth/password-reset", accounts.PasswordResetRequestView.as_view(),
         name="password-reset-request"),
    path("auth/password-reset/check", accounts.PasswordResetCheckView.as_view(),
         name="password-reset-check"),
    path("auth/password-reset/confirm", accounts.PasswordResetConfirmView.as_view(),
         name="password-reset-confirm"),
    path("register", accounts.RegisterView.as_view(), name="merchant-register"),
    path("register/verify", accounts.RegisterVerifyView.as_view(),
         name="merchant-register-verify"),
    path("me", auth.MeView.as_view(), name="staff-me"),
    path("merchant", merchant.OwnMerchantView.as_view(), name="own-merchant"),
    path("merchant/api-key", merchant.OwnApiKeyView.as_view(), name="own-api-key"),
    path("merchant/webhook", merchant.OwnWebhookView.as_view(), name="own-webhook"),
    path("payments", payments.PaymentListView.as_view(), name="staff-payments"),
    path("payments/<str:payment_id>", payments.PaymentDetailView.as_view(),
         name="staff-payment-detail"),
    path("payments/<str:payment_id>/refunds", payments.RefundView.as_view(),
         name="staff-refund"),
    path("payments/<str:payment_id>/capture", payments.CaptureView.as_view(),
         name="staff-capture"),
    path("payments/<str:payment_id>/cancel", payments.CancelView.as_view(),
         name="staff-cancel"),
    path("operations/<str:operation_id>/recheck", payments.OperationRecheckView.as_view(),
         name="staff-operation-recheck"),
    path("reviews", reviews.ReviewListView.as_view(), name="review-list"),
    path("reviews/<str:case_id>", reviews.ReviewDetailView.as_view(), name="review-detail"),
    path("merchants", admin.MerchantListView.as_view(), name="merchant-admin"),
    path("merchants/<str:merchant_id>/approve", admin.MerchantApproveView.as_view(),
         name="merchant-approve"),
    path("merchants/<str:merchant_id>/reject", admin.MerchantRejectView.as_view(),
         name="merchant-reject"),
    path("merchants/<str:merchant_id>/webhook", admin.MerchantWebhookView.as_view(),
         name="merchant-webhook"),
    path("audit", admin.AuditListView.as_view(), name="audit-list"),
    # Signed by the simulator, not a staff call (SIMULATOR-CONTRACT.md section 9).
    path("simulator/notifications", SimulatorNotificationView.as_view(),
         name="simulator-notifications"),
]
