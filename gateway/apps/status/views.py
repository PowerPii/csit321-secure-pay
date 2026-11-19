"""GET /status.json: the public status page's data (apps.status.service.build_status).

Public and read-only: no personal or payment data, only whether each part answered. Any site
may read it (the status page is on the marketing website's domain), with no cookies. Built
at most once a minute and shared through the cache, so a busy page costs the database little.
"""
import logging
from typing import ClassVar

from django.core.cache import cache
from django.db import DatabaseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.throttling import AnonRateThrottle

from . import service

logger = logging.getLogger(__name__)

CACHE_KEY = "status:page"
CACHE_SECONDS = 60


class PublicStatusView(APIView):
    permission_classes: ClassVar = [AllowAny]
    authentication_classes: ClassVar = []
    throttle_classes: ClassVar = [AnonRateThrottle]
    schema = None

    def check_throttles(self, request):
        # The rate limit's counter lives in the database. If that cannot be read, answer
        # anyway: this page exists to say the database is down (completion audit, 19 Nov 2026).
        try:
            super().check_throttles(request)
        except DatabaseError:
            logger.warning("Status page: rate limit counter not readable")

    def get(self, request):
        try:
            data = cache.get(CACHE_KEY)
            if data is None:
                data = service.build_status()
                cache.set(CACHE_KEY, data, CACHE_SECONDS)
        except DatabaseError:
            logger.warning("Status page: database not readable")
            data = service.database_down_status()
        return Response(data)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Access-Control-Allow-Origin"] = "*"
        response["Cache-Control"] = "public, max-age=30"
        response["X-Robots-Tag"] = "noindex"
        return response
