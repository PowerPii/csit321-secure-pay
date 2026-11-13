from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from apps.common.views import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", HealthView.as_view(), name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("v1/", include("apps.payments.urls")),
    path("v1/", include("apps.refunds.urls")),
    path("checkout/", include("apps.checkout.urls")),
    path("guest/status/", include("apps.guest.urls")),
    path("internal/", include("apps.internal.urls")),
]
