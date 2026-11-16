"""Merchant self-registration (FR-MER-01, FR-MER-02, UC-15; wireframe D7).

1. `register()`: checks the business details, then creates a pending merchant and an inactive
   merchant operator account, and queues an email verification link (valid for
   MERCHANT_VERIFICATION_LINK_TTL_HOURS, works once). A UEN that is already registered is an
   error, as UC-15 says. An email address that already has an account gets the same reply as
   a new one; its holder is told by email instead, so the form cannot be used to find out
   which addresses have accounts.
2. `verify_email()`: activates the operator account (it can now sign in, but the merchant has
   no API key until approval) and notifies every administrator (FR-MER-02).

An unverified registration whose link has expired no longer holds its UEN or email address:
the next registration that needs either one removes it. A rejected registration frees both.
"""
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts import mail, tokens
from apps.accounts.models import AccountToken, Role, StaffAccount
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid
from apps.events.models import OutboundEmail
from apps.merchants.models import Merchant

PURPOSE = AccountToken.Purpose.EMAIL_VERIFICATION

# Singapore UEN formats: businesses (8 digits + letter), local companies (year + 5 digits +
# letter), and other entities (T/S/R + 2 digits + 2-letter type + 4 digits + letter).
UEN_PATTERN = re.compile(r"^(\d{8}[A-Z]|\d{9}[A-Z]|[TSR]\d{2}[A-Z]{2}\d{4}[A-Z])$")


def _ttl() -> timedelta:
    return timedelta(hours=settings.GATEWAY_RULES["MERCHANT_VERIFICATION_LINK_TTL_HOURS"])


def sent_message(email: str) -> str:
    hours = settings.GATEWAY_RULES["MERCHANT_VERIFICATION_LINK_TTL_HOURS"]
    return (f"We have sent a verification link to {email}. Open it within {hours} hours to "
            "finish the registration.")


def _text(body: dict, field: str, label: str, max_length: int) -> str:
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise invalid("missing_field", f"Enter the {label}.", param=field)
    value = " ".join(value.split())
    if len(value) > max_length:
        raise invalid("invalid_field", f"The {label} can be up to {max_length} characters.",
                      param=field)
    return value


def clean(body: dict) -> dict:
    """The D7 fields, checked one by one so the page can mark the field to correct."""
    name = _text(body, "business_name", "business name", 120)
    uen = _text(body, "registration_number", "registration number (UEN)", 10).upper()
    uen = uen.replace(" ", "")
    if not UEN_PATTERN.match(uen):
        raise invalid("invalid_field", "Enter a valid UEN, for example 202612345K.",
                      param="registration_number")
    website = _text(body, "website", "website", 300)
    try:
        URLValidator(schemes=["https", "http"])(website)
    except ValidationError:
        raise invalid("invalid_field", "Enter the website as an address starting with "
                      "https://.", param="website") from None
    contact = _text(body, "contact_name", "contact name", 120)
    email = _text(body, "email", "contact email", 254).lower()
    try:
        validate_email(email)
    except ValidationError:
        raise invalid("invalid_field", "Enter a valid email address.", param="email") from None
    password = body.get("password")
    if not isinstance(password, str) or not password:
        raise invalid("missing_field", "Choose a password.", param="password")
    try:
        validate_password(password, get_user_model()(username=email, email=email))
    except ValidationError as exc:
        raise invalid("weak_password", " ".join(exc.messages), param="password") from None
    if body.get("confirmed") is not True:
        raise invalid("missing_field", "Confirm that the business details are correct.",
                      param="confirmed")
    return {"name": name, "uen": uen, "website": website, "contact": contact, "email": email,
            "password": password[:256]}


def _stale(merchant: Merchant) -> bool:
    return (merchant.status == Merchant.Status.PENDING and merchant.email_verified_at is None
            and merchant.created_at <= timezone.now() - _ttl())


def _remove(merchant: Merchant) -> None:
    """Delete an expired, never verified registration (it has no key and no payments)."""
    for account in StaffAccount.objects.filter(merchant=merchant).select_related("user"):
        user = account.user
        account.delete()
        user.delete()
    merchant.delete()


def _purge_stale(uen: str, email: str) -> None:
    candidates = Merchant.objects.filter(
        Q(registration_number=uen) | Q(staff__user__email__iexact=email),
        status=Merchant.Status.PENDING, email_verified_at__isnull=True).distinct()
    for merchant in candidates:
        if _stale(merchant):
            _remove(merchant)
    # A rejected registration keeps its merchant row (and the audit trail), but frees the
    # contact email so the business can register again with corrected details.
    for account in StaffAccount.objects.filter(
            user__email__iexact=email, user__is_active=False,
            merchant__status=Merchant.Status.REJECTED).select_related("user"):
        user = account.user
        account.delete()
        user.delete()


def already_registered() -> ApiError:
    return ApiError(409, "business_already_registered", "This business is already registered.",
                    param="registration_number")


def register(request, body: dict) -> str:
    """Returns the reply message. Raises ApiError for fields to correct."""
    data = clean(body)
    User = get_user_model()
    with transaction.atomic():
        _purge_stale(data["uen"], data["email"])
        if Merchant.objects.filter(registration_number=data["uen"]).exclude(
                status=Merchant.Status.REJECTED).exists():
            raise already_registered()
        if User.objects.filter(Q(username__iexact=data["email"])
                               | Q(email__iexact=data["email"])).exists():
            # Same reply as a new registration; the holder of the address is told instead.
            mail.notice(data["email"], "someone tried to register with your email",
                        "Hello,\n\nSomeone tried to register a business on SecurePay with this "
                        "email address, which already has an account. Nothing was changed.\n\n"
                        "If it was you, sign in at "
                        f"{mail.dashboard_link('login')} or reset your password at "
                        f"{mail.dashboard_link('forgot-password')}.")
            return sent_message(data["email"])
        merchant = Merchant(
            name=data["name"], registration_number=data["uen"], website=data["website"],
            contact_name=data["contact"], contact_email=data["email"])
        try:
            with transaction.atomic():
                merchant.save()
        except IntegrityError:  # the same UEN registered a moment ago
            raise already_registered() from None
        first, _, last = data["contact"].partition(" ")
        user = User(username=data["email"], email=data["email"], first_name=first[:150],
                    last_name=last[:150], is_active=False)
        user.set_password(data["password"])
        user.save()
        account = StaffAccount.objects.create(user=user, role=Role.MERCHANT_OPERATOR,
                                              merchant=merchant)
        token = tokens.issue(user, PURPOSE, _ttl())
        hours = settings.GATEWAY_RULES["MERCHANT_VERIFICATION_LINK_TTL_HOURS"]
        mail.queue(
            OutboundEmail.Kind.EMAIL_VERIFICATION, data["email"], "verify your email",
            f"Hello {first},\n\nThank you for registering {merchant.name} with SecurePay. "
            f"Open this link within {hours} hours to verify your email address:\n\n"
            f"{mail.dashboard_link('register/verify', token)}\n\n"
            "After that an administrator reviews the registration. Once it is approved you "
            "can sign in and generate your API key.\n\nIf you did not register, ignore this "
            "email.",
            discard_after=timezone.now() + _ttl())
        audit("merchant.registered", actor_type=AuditEvent.ActorType.STAFF,
              actor_id=account.public_id, merchant_id=merchant.public_id,
              target_type="merchant", target_id=merchant.public_id,
              request_id=getattr(request, "request_id", ""),
              details={"registration_number": merchant.registration_number})
    return sent_message(data["email"])


def verify_email(request, token) -> Merchant:
    with transaction.atomic():
        row = tokens.consume(PURPOSE, token)
        account = (StaffAccount.objects.select_related("user", "merchant")
                   .filter(user=row.user).first())
        if account is None or account.merchant is None:
            raise tokens.link_invalid()
        merchant = Merchant.objects.select_for_update().get(pk=account.merchant_id)
        if merchant.status != Merchant.Status.PENDING:
            raise tokens.link_invalid()
        user = account.user
        user.is_active = True
        user.save(update_fields=["is_active"])
        merchant.email_verified_at = timezone.now()
        merchant.save(update_fields=["email_verified_at", "updated_at"])
        audit("merchant.email_verified", actor_type=AuditEvent.ActorType.STAFF,
              actor_id=account.public_id, merchant_id=merchant.public_id,
              target_type="merchant", target_id=merchant.public_id,
              request_id=getattr(request, "request_id", ""))
        notified = mail.notify_administrators(
            f"new merchant registration: {merchant.name}",
            f"Hello,\n\n{merchant.name} (UEN {merchant.registration_number}) has registered "
            f"and verified {merchant.contact_email}. It is waiting for approval.\n\n"
            f"Contact: {merchant.contact_name}\nWebsite: {merchant.website}\n\n"
            f"Review it at {mail.dashboard_link('merchants')}.")
        audit("merchant.administrators_notified", actor_type=AuditEvent.ActorType.SYSTEM,
              actor_id="registration", merchant_id=merchant.public_id,
              target_type="merchant", target_id=merchant.public_id,
              details={"administrators": notified})
    return merchant
