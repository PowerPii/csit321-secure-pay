"""Base view for the merchant API (/v1): API key auth, per-key throttle, signed replies."""
from typing import ClassVar

from django.template.response import SimpleTemplateResponse
from rest_framework.views import APIView

from apps.events import signing
from apps.merchants.auth import ApiKeyAuthentication, ApiKeyRateThrottle, IsActiveMerchant
from apps.merchants.models import ApiKey


class MerchantAPIView(APIView):
    """Every reply to a request with a valid API key is signed with the merchant's signing
    secret, errors included (API-CONTRACT.md section 2, FR-TXN-08/10). 401 replies are not
    signed because the merchant is unknown."""

    authentication_classes: ClassVar = [ApiKeyAuthentication]
    permission_classes: ClassVar = [IsActiveMerchant]
    throttle_classes: ClassVar = [ApiKeyRateThrottle]

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
