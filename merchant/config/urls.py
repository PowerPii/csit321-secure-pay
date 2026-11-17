from django.conf import settings
from django.contrib import admin
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.decorators.cache import never_cache


@never_cache
def healthz(request):
    """For the uptime monitor and the server watchdog: 200 when the shop's database answers."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "degraded", "problems": ["database"]}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz", healthz),
    path("webhooks/", include("apps.webhooks.urls")),
    path("", include("apps.shop.urls")),
]

if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path("admin/", admin.site.urls))
