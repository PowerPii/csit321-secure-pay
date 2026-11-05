from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", lambda r: JsonResponse({"status": "ok"})),
    path("sim/", include("apps.operations.urls")),
]
