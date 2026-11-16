from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

urlpatterns = [
    path("healthz", lambda r: JsonResponse({"status": "ok"})),
    path("sim/", include("apps.operations.urls")),
]

if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path("admin/", admin.site.urls))
