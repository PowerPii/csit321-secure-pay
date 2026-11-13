"""Merchant payment endpoints: POST /v1/payments and GET /v1/payments/{id} (UC-57, UC-28)."""
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, URLValidator
from rest_framework import status
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid, not_found
from apps.merchants.api import MerchantAPIView
from apps.payments.idempotency import run_idempotent
from apps.payments.models import Payment
from apps.payments.serializers import payment_to_dict

CREATE_FIELDS = ("amount", "currency", "order_reference", "return_url", "customer_email",
                 "description")
REQUIRED_FIELDS = ("amount", "currency", "order_reference", "return_url")
PRINTABLE_ASCII = re.compile(r"^[\x20-\x7E]+$")


def validate_create(body: dict, merchant) -> dict:
    """Check a create-payment body against CreatePaymentRequest; return clean fields."""
    rules = settings.GATEWAY_RULES
    for name in body:
        if name not in CREATE_FIELDS:
            raise invalid("invalid_field", f"Unknown field '{name}'.", param=name)
    for name in REQUIRED_FIELDS:
        if body.get(name) is None:
            raise invalid("missing_field", f"'{name}' is required.", param=name)

    amount = body["amount"]
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise invalid("invalid_field", "'amount' must be an integer number of cents.",
                      param="amount")
    if amount < rules["MIN_AMOUNT_CENTS"]:
        raise invalid("amount_too_small",
                      f"The minimum amount is {rules['MIN_AMOUNT_CENTS']} cents.", param="amount")
    if amount > rules["MAX_AMOUNT_CENTS"]:
        raise invalid("amount_too_large",
                      f"The maximum amount is {rules['MAX_AMOUNT_CENTS']} cents.", param="amount")

    if body["currency"] != rules["CURRENCY"]:
        raise invalid("currency_not_supported", f"Only {rules['CURRENCY']} is supported.",
                      param="currency")

    order_reference = body["order_reference"]
    if (not isinstance(order_reference, str) or not 1 <= len(order_reference) <= 64
            or not PRINTABLE_ASCII.match(order_reference)):
        raise invalid("invalid_field", "'order_reference' must be 1 to 64 printable ASCII "
                      "characters.", param="order_reference")

    return_url = body["return_url"]
    if not isinstance(return_url, str) or len(return_url) > 2048:
        raise invalid("invalid_field", "'return_url' must be a URL of at most 2048 characters.",
                      param="return_url")
    try:
        URLValidator(schemes=["http", "https"])(return_url)
    except ValidationError:
        raise invalid("invalid_field", "'return_url' is not a valid URL.",
                      param="return_url") from None
    if not return_url.lower().startswith("https://"):
        raise invalid("return_url_not_https", "'return_url' must use HTTPS.", param="return_url")

    customer_email = body.get("customer_email")
    if customer_email is not None:
        try:
            if not isinstance(customer_email, str) or len(customer_email) > 254:
                raise ValidationError("bad")
            EmailValidator()(customer_email)
        except ValidationError:
            raise invalid("invalid_field", "'customer_email' is not a valid email address.",
                          param="customer_email") from None

    description = body.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 200):
        raise invalid("invalid_field", "'description' must be text of at most 200 characters.",
                      param="description")

    if merchant.max_amount_cents is not None and amount > merchant.max_amount_cents:
        raise ApiError(422, "amount_above_merchant_limit",
                       "The amount is above the limit set for your account.", param="amount")

    return {
        "amount": amount,
        "currency": rules["CURRENCY"],
        "order_reference": order_reference,
        "return_url": return_url,
        "customer_email": customer_email or "",
        "description": description or "",
    }


class PaymentListView(MerchantAPIView):
    def post(self, request):
        merchant, api_key = request.user, request.auth

        def create(body):
            fields = validate_create(body, merchant)
            payment = Payment.create_for_merchant(merchant, **fields)
            audit(
                "payment.created",
                actor_type=AuditEvent.ActorType.MERCHANT_API,
                actor_id=api_key.public_id,
                merchant_id=merchant.public_id,
                target_type="payment",
                target_id=payment.public_id,
                request_id=request.request_id,
                details={"amount": payment.amount, "order_reference": payment.order_reference},
            )
            return Response(payment_to_dict(payment), status=status.HTTP_201_CREATED)

        return run_idempotent(request, create)


class PaymentDetailView(MerchantAPIView):
    def get(self, request, payment_id: str):
        # Another merchant's payment is indistinguishable from one that does not exist.
        payment = Payment.objects.filter(public_id=payment_id, merchant=request.user).first()
        if payment is None:
            raise not_found()
        return Response(payment_to_dict(payment))

