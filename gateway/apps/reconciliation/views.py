"""Simulator notifications (SIMULATOR-CONTRACT.md section 9, FR-SIM-02).

`POST /internal/simulator/notifications`: a signed `operation.recorded` message. It is
evidence equal to a status-query reply, so it goes through the same apply functions
(apps.payments.reconciliation._apply), which change an operation only while it is
`pending` or `unresolved`. A repeat, a late copy or one for an operation that is already
final changes nothing and still gets 200. The simulator does not retry; the status query
stays the safety net, so anything we cannot use is simply ignored.
"""
import json
import logging
from typing import ClassVar

from django.conf import settings
from rest_framework.parsers import BaseParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.errors import invalid
from apps.events import signing
from apps.payments.models import Operation
from apps.payments.processor import SIGNATURE_HEADER, Answer, AnswerKind

logger = logging.getLogger(__name__)


class RawParser(BaseParser):
    """Keep the exact bytes: the signature covers the raw body."""

    media_type = "application/json"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read()


class SimulatorNotificationView(APIView):
    authentication_classes: ClassVar = []
    permission_classes: ClassVar = [AllowAny]
    parser_classes: ClassVar = [RawParser]
    throttle_classes: ClassVar = []

    def post(self, request):
        raw = request.body
        tolerance = settings.GATEWAY_RULES["SIMULATOR_SIGNATURE_TOLERANCE_SECONDS"]
        signature = request.headers.get(SIGNATURE_HEADER, "")
        if not signature or not signing.verify(raw, signature, settings.SIMULATOR_SIGNING_SECRET,
                                               tolerance):
            raise invalid("signature_invalid", "Missing or invalid Simulator-Signature.")
        try:
            note = json.loads(raw)
            record = note["data"]
            operation_id = record["operation_id"]
        except (ValueError, KeyError, TypeError):
            raise invalid("invalid_json", "Not an operation.recorded notification.") from None
        if note.get("type") != "operation.recorded" or record.get("status") not in (
                "approved", "declined"):
            return Response({"received": True, "applied": False})
        operation = (Operation.objects.select_related("payment__merchant")
                     .filter(public_id=operation_id).first())
        applied = False
        if operation is not None and operation.status in Operation.OPEN_STATUSES and (
                record.get("payment_id") == operation.payment.public_id):
            from apps.payments.reconciliation import _apply

            _apply(operation, Answer(AnswerKind.RECORDED, record=record,
                                     raw_body=raw.decode(), signature=signature),
                   request_id=getattr(request, "request_id", ""))
            operation.refresh_from_db()
            applied = operation.status not in Operation.OPEN_STATUSES
        logger.info("Simulator notification %s copy %s for %s: applied=%s", note.get("id"),
                    note.get("delivery"), operation_id, applied)
        return Response({"received": True, "applied": applied})
