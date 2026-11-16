"""Customer account API (screens C10 to C12), served under /customer/."""
from django.urls import path

from apps.customers import views

urlpatterns = [
    path("register", views.RegisterView.as_view(), name="customer-register"),
    path("sign-in", views.SignInView.as_view(), name="customer-sign-in"),
    path("sign-out", views.SignOutView.as_view(), name="customer-sign-out"),
    path("sign-out-everywhere", views.SignOutEverywhereView.as_view(),
         name="customer-sign-out-everywhere"),
    path("me", views.MeView.as_view(), name="customer-me"),
    path("password", views.PasswordView.as_view(), name="customer-password"),
    path("payments", views.PaymentsView.as_view(), name="customer-payments"),
    path("payments/<str:reference>", views.PaymentDetailView.as_view(),
         name="customer-payment"),
    path("password-reset/request", views.ResetRequestView.as_view(),
         name="customer-reset-request"),
    path("password-reset/check", views.ResetCheckView.as_view(), name="customer-reset-check"),
    path("password-reset/confirm", views.ResetConfirmView.as_view(),
         name="customer-reset-confirm"),
]
