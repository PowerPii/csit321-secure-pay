"""One-time link tokens (API-CONTRACT.md section 9).

`issue()` returns the plaintext once, for the emailed link; only its SHA-256 digest is kept.
`peek()` finds a usable token without using it (to show the right form); `consume()` uses it
inside the caller's transaction, under a row lock, so two requests cannot both use one link.
"""
import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import AccountToken
from apps.common.errors import ApiError


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _owner(owner) -> dict:
    """A Django user (staff, merchant registration) or a customer account."""
    if owner._meta.label_lower == "customers.customeraccount":
        return {"customer": owner}
    return {"user": owner}


def issue(owner, purpose: str, ttl: timedelta) -> str:
    """A new token for the owner; earlier unused tokens for the same purpose stop working."""
    now = timezone.now()
    AccountToken.objects.filter(**_owner(owner), purpose=purpose, used_at__isnull=True).update(
        used_at=now)
    token = secrets.token_urlsafe(32)  # 32 random bytes
    AccountToken.objects.create(**_owner(owner), purpose=purpose, digest=_digest(token),
                                expires_at=now + ttl)
    return token


def link_invalid() -> ApiError:
    # One reply for unknown, expired, used and withdrawn links: none of them says more.
    return ApiError(400, "link_invalid", "This link has expired or has already been used. "
                    "Ask for a new one.", param="token")


def _usable(purpose: str, token, lock: bool) -> AccountToken:
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        raise link_invalid()
    rows = AccountToken.objects.select_related("user", "customer")
    if lock:
        rows = rows.select_for_update(of=("self",))  # owners are outer joins now
    row = rows.filter(digest=_digest(token), purpose=purpose).first()
    if row is None or row.used_at is not None or timezone.now() >= row.expires_at:
        raise link_invalid()
    return row


def peek(purpose: str, token) -> AccountToken:
    return _usable(purpose, token, lock=False)


def consume(purpose: str, token) -> AccountToken:
    """Call inside transaction.atomic(). Marks the token used and returns it."""
    row = _usable(purpose, token, lock=True)
    row.used_at = timezone.now()
    row.save(update_fields=["used_at"])
    return row


def recent_count(owner, purpose: str, minutes: int) -> int:
    since = timezone.now() - timedelta(minutes=minutes)
    return AccountToken.objects.filter(**_owner(owner), purpose=purpose,
                                       created_at__gte=since).count()
