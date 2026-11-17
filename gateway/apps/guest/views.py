"""Guest status API for the checkout front end (screen C9; openapi/guest-status.v1.yaml).

Same origin as the page, JSON only (a cross-site form cannot post JSON without a CORS
preflight), and the session cookie is SameSite=Strict, HttpOnly, Secure and limited to
/guest/status, so another site can neither send nor read it.
"""
from django.conf import settings
from rest_framework.response import Response

from apps.common.clientip import client_ip
from apps.common.views import PublicJSONView
from apps.guest import receipts, service


class GuestView(PublicJSONView):
    @staticmethod
    def token(request) -> str | None:
        return request.COOKIES.get(service.COOKIE)


class CodeView(GuestView):
    def post(self, request):
        return Response(service.request_code(self.body(request), client_ip(request)),
                        status=202)


class VerifyView(GuestView):
    def post(self, request):
        payment, token = service.verify_code(self.body(request))
        response = Response(service.to_view(payment))
        response.set_cookie(
            service.COOKIE, token, path=service.COOKIE_PATH, httponly=True, secure=True,
            samesite="Strict",
            max_age=settings.GATEWAY_RULES["GUEST_STATUS_SESSION_MINUTES"] * 60)
        return response


class PaymentView(GuestView):
    def get(self, request):
        return Response(service.to_view(service.session_payment(self.token(request))))


class ReceiptView(GuestView):
    """GET -> the payment's receipt as a PDF (same session as the status view)."""

    def get(self, request):
        return receipts.pdf_response(service.session_payment(self.token(request)))


class SignOutView(GuestView):
    def post(self, request):
        service.end_session(self.token(request))
        response = Response(status=204)
        response.delete_cookie(service.COOKIE, path=service.COOKIE_PATH, samesite="Strict")
        return response
