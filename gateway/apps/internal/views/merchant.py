"""A merchant operator's own merchant (wireframe D8): approval status, API key and webhook
address.

* GET /internal/merchant: status, key hint, webhook address and whether it is approved.
* POST /internal/merchant/api-key: once the merchant is approved and has no active key, issue
  one with a fresh signing secret, shown once (FR-MER-03). Rotation and revocation are later
  Should items (FR-MER-04, FR-MER-05), so a second key is refused.
* POST /internal/merchant/webhook {webhook_url}: submit the address for administrator approval
  (FR-MER-10). A new address is never used until an administrator approves it (FR-ADM-13).
"""
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from apps.accounts import mail
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid
from apps.common.timefmt import rfc3339
from apps.internal.access import OPERATOR, StaffAPIView
from apps.internal.views.admin import _webhook_url
from apps.merchants.models import ApiKey, Merchant


def own_merchant_to_dict(merchant: Merchant) -> dict:
    key = merchant.api_keys.filter(revoked_at__isnull=True).first()
    return {
        "id": merchant.public_id,
        "name": merchant.name,
        "status": merchant.status,
        "registration_number": merchant.registration_number or None,
        "webhook_url": merchant.webhook_url or None,
        "webhook_url_approved": merchant.webhook_url_approved,
        "api_key": ({"id": key.public_id, "hint": key.hint + "…",
                     "created_at": rfc3339(key.created_at),
                     "last_used_at": rfc3339(key.last_used_at)} if key else None),
        "can_generate_key": merchant.is_active_merchant and key is None,
    }


class _OwnMerchantView(StaffAPIView):
    roles = OPERATOR

    def _audit(self, action, merchant, target_type="merchant", target_id=None, **details):
        audit(action, actor_type=AuditEvent.ActorType.STAFF, actor_id=self.staff.public_id,
              merchant_id=merchant.public_id, target_type=target_type,
              target_id=target_id or merchant.public_id, request_id=self.request.request_id,
              details=details)

    def _locked_merchant(self) -> Merchant:
        return Merchant.objects.select_for_update().get(pk=self.staff.merchant_id)


class OwnMerchantView(_OwnMerchantView):
    def get(self, request):
        return Response(own_merchant_to_dict(self.staff.merchant))


class OwnApiKeyView(_OwnMerchantView):
    def post(self, request):
        with transaction.atomic():
            merchant = self._locked_merchant()
            if not merchant.is_active_merchant:
                raise ApiError(409, "merchant_not_approved", "An API key can be generated once "
                               "an administrator has approved the merchant.")
            if merchant.api_keys.filter(revoked_at__isnull=True).exists():
                raise ApiError(409, "api_key_exists", "This merchant already has an active API "
                               "key. Key rotation is not available yet.")
            secret = merchant.rotate_signing_secret()
            merchant.save(update_fields=["signing_secret_encrypted", "updated_at"])
            api_key, plaintext = ApiKey.issue(merchant)
            self._audit("api_key.issued", merchant, target_type="api_key",
                        target_id=api_key.public_id)
        data = own_merchant_to_dict(merchant)
        data["credentials"] = {"api_key": plaintext, "signing_secret": secret}
        return Response(data, status=status.HTTP_201_CREATED)


class OwnWebhookView(_OwnMerchantView):
    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        url = _webhook_url(body.get("webhook_url"))
        if not url:
            raise invalid("missing_field", "Enter the webhook URL.", param="webhook_url")
        with transaction.atomic():
            merchant = self._locked_merchant()
            if merchant.status in (Merchant.Status.REJECTED, Merchant.Status.SUSPENDED):
                raise ApiError(409, "merchant_not_active", "This merchant cannot change its "
                               "webhook address.")
            if url == merchant.webhook_url:
                return Response(own_merchant_to_dict(merchant))
            merchant.webhook_url = url
            merchant.webhook_url_approved = False  # until an administrator approves it
            merchant.save(update_fields=["webhook_url", "webhook_url_approved", "updated_at"])
            self._audit("merchant.webhook_submitted", merchant, webhook_url=url)
            mail.notify_administrators(
                f"webhook address to approve for {merchant.name}",
                f"Hello,\n\n{merchant.name} submitted a webhook address for approval:\n\n{url}"
                f"\n\nNo webhooks go to it until it is approved. Review it at "
                f"{mail.dashboard_link('merchants')}.")
        return Response(own_merchant_to_dict(merchant))
