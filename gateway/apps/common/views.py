"""Shared view helpers."""
from typing import ClassVar

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class NotImplementedView(APIView):
    """Placeholder for a routed endpoint that has not been built yet.

    Each route in the MVP is wired to one of these so the URL map, OpenAPI schema and
    frontend can be built against the real paths. Replace it with the real view.
    """

    permission_classes: ClassVar = [AllowAny]
    schema = None  # left out of the OpenAPI file until built
    todo: str = ""

    def _reply(self, request, *args, **kwargs):
        return Response(
            {"error": "not_implemented", "todo": self.todo},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    get = post = put = patch = delete = _reply


def todo(description: str):
    """Return a NotImplementedView bound to a short description of the work left."""
    return NotImplementedView.as_view(todo=description)


class HealthView(APIView):
    permission_classes: ClassVar = [AllowAny]
    authentication_classes: ClassVar = []
    schema = None

    def get(self, request):
        return Response({"status": "ok"})
