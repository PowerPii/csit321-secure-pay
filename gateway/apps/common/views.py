"""Shared view helpers."""
from typing import ClassVar

from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.common.errors import invalid


def body_or_empty(request) -> dict:
    """For endpoints whose field validators handle absent or non-object input."""
    return request.data if isinstance(request.data, dict) else {}


class PublicJSONView(APIView):
    """Same-origin customer APIs; session checks remain in each endpoint's service."""

    authentication_classes: ClassVar = []
    permission_classes: ClassVar = [AllowAny]
    parser_classes: ClassVar = [JSONParser]
    throttle_classes: ClassVar = [AnonRateThrottle]

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
