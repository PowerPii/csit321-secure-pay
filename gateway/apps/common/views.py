"""Shared view helpers."""
from typing import ClassVar

from rest_framework.exceptions import UnsupportedMediaType
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.errors import invalid
from apps.common.throttling import AnonRateThrottle


def body_or_empty(request) -> dict:
    """For endpoints whose field validators handle absent or non-object input."""
    return request.data if isinstance(request.data, dict) else {}


class PublicJSONView(APIView):
    """Same-origin customer APIs; session checks remain in each endpoint's service."""

    authentication_classes: ClassVar = []
    permission_classes: ClassVar = [AllowAny]
    parser_classes: ClassVar = [JSONParser]
    throttle_classes: ClassVar = [AnonRateThrottle]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Every unsafe request must say it is JSON, even one whose view never reads the body
        # (submit, resend, sign-out). A cross-site HTML form can only send form or text
        # types, so it is refused here before any view runs.
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.content_type.split(
                ";")[0].strip().lower() != "application/json":
            raise UnsupportedMediaType(request.content_type)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["X-Robots-Tag"] = "noindex"
        return response

    @staticmethod
    def body(request) -> dict:
        if not isinstance(request.data, dict):
            raise invalid("invalid_json", "The request body must be a JSON object.")
        return request.data


class HealthView(APIView):
    permission_classes: ClassVar = [AllowAny]
    authentication_classes: ClassVar = []
    schema = None

    def get(self, request):
        return Response({"status": "ok"})


# The worker writes its heartbeat every 15 s; two minutes without one means it has stopped.
WORKER_STALE_AFTER_SECONDS = 120


def readiness_problems() -> list[str]:
    """What stops the gateway from doing its whole job right now (empty = ready)."""
    from datetime import timedelta

    from django.db import DatabaseError, connections
    from django.utils import timezone

    from apps.events.models import WorkerHeartbeat

    problems = []
    for alias, name in (("default", "database"), ("vault", "vault")):
        try:
            with connections[alias].cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError:
            problems.append(name)
    if "database" not in problems:
        cutoff = timezone.now() - timedelta(seconds=WORKER_STALE_AFTER_SECONDS)
        if not WorkerHeartbeat.objects.filter(name="worker", seen_at__gte=cutoff).exists():
            problems.append("worker")
    return problems


class ReadinessView(APIView):
    """/readyz for uptime monitors: 200 when the databases answer and the worker is alive,
    503 with the failing part names otherwise. /healthz only says the web process is up."""

    permission_classes: ClassVar = [AllowAny]
    authentication_classes: ClassVar = []
    schema = None

    def get(self, request):
        problems = readiness_problems()
        response = Response({"status": "degraded", "problems": problems} if problems
                            else {"status": "ok"}, status=503 if problems else 200)
        response["Cache-Control"] = "no-store"
        return response
