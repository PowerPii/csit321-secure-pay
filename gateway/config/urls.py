from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from apps.common.views import HealthView

urlpatterns = [
    path("healthz", HealthView.as_view(), name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("v1/", include("apps.payments.urls")),
    path("v1/", include("apps.refunds.urls")),
    path("checkout/", include("apps.checkout.urls")),
    path("guest/status/", include("apps.guest.urls")),
    path("customer/", include("apps.customers.urls")),
    path("internal/", include("apps.internal.urls")),
]

if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path("admin/", admin.site.urls))
