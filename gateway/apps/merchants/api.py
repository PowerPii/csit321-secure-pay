"""Base view for the merchant API (/v1): API key auth, per-key throttle, signed replies."""
from typing import ClassVar

from django.template.response import SimpleTemplateResponse
from rest_framework.views import APIView

from apps.events import signing
from apps.merchants.auth import (
    ApiKeyAuthentication,
    ApiKeyRateThrottle,
    IsActiveMerchant,
    MerchantIpRateThrottle,
)
from apps.merchants.models import ApiKey


class MerchantAPIView(APIView):
    """Every reply to a request with a valid API key is signed with the merchant's signing
    secret, errors included (API-CONTRACT.md section 2, FR-TXN-08/10). 401 replies are not
    signed because the merchant is unknown."""

    authentication_classes: ClassVar = [ApiKeyAuthentication]
    permission_classes: ClassVar = [IsActiveMerchant]
    throttle_classes: ClassVar = [ApiKeyRateThrottle, MerchantIpRateThrottle]

    def check_throttles(self, request):
        """As DRF's, but each rejection is recorded as a violation (UC-43)."""
        from apps.common.clientip import client_ip
        from apps.security.limits import record_violation

        waits = []
        for throttle in self.get_throttles():
            if not throttle.allow_request(request, self):
                wait = throttle.wait()
                waits.append(wait)
                api_key = request.auth if isinstance(request.auth, ApiKey) else None
                merchant_id = api_key.merchant.public_id if api_key else ""
                if isinstance(throttle, ApiKeyRateThrottle) and api_key:
                    record_violation(request, source=api_key.public_id, scope="api_key",
                                     merchant_id=merchant_id, wait=wait)
                else:
                    record_violation(request, source=client_ip(request) or "unknown",
                                     scope="ip", merchant_id=merchant_id, wait=wait)
        if waits:
            self.throttled(request, max((w for w in waits if w is not None), default=None))

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        api_key = getattr(request, "_auth", None)
        if isinstance(api_key, ApiKey) and response.status_code == 404:
            # FR-MER-09: another merchant's record answers 404; log the attempt behind it.
            from apps.audit.models import AuditEvent
            from apps.security.crossmerchant import log_if_cross_merchant

            log_if_cross_merchant(request, kwargs, api_key.merchant,
                                  AuditEvent.ActorType.MERCHANT_API, api_key.public_id)
        if isinstance(api_key, ApiKey) and response.status_code != 401:
            secret = api_key.merchant.signing_secret

            def add_signature(resp):
                resp[signing.HEADER] = signing.sign(resp.content, secret)

            if isinstance(response, SimpleTemplateResponse) and not response.is_rendered:
                response.add_post_render_callback(add_signature)
            else:
                add_signature(response)
        return response
