"""Account emails through the outbox (apps.events.emails).

Queued in the caller's transaction and sent by the worker, so a request takes the same time
whether or not an email goes out (FR-ACC-07: the reply must not reveal registered emails).
A link email is discarded unsent once its token has expired.
"""
from django.conf import settings

from apps.events import emails
from apps.events.models import OutboundEmail

SIGN_OFF = "\n\nSecurePay"


def dashboard_link(path: str, token: str | None = None) -> str:
    # The token goes in the fragment: browsers never send it to a server or in a Referer.
    return f"{settings.DASHBOARD_URL}/{path.lstrip('/')}" + (f"#token={token}" if token else "")


def queue(kind: str, to: str, subject: str, body: str, discard_after=None) -> OutboundEmail:
    return emails.queue(kind, None, to, f"SecurePay: {subject}", body + SIGN_OFF,
                        discard_after=discard_after)


def notice(to: str, subject: str, body: str) -> OutboundEmail:
    return queue(OutboundEmail.Kind.ACCOUNT_NOTICE, to, subject, body)


def administrators() -> list[str]:
    from apps.accounts.models import Role, StaffAccount

    return list(StaffAccount.objects.filter(role=Role.ADMINISTRATOR, user__is_active=True)
                .values_list("user__email", flat=True))


def notify_administrators(subject: str, body: str) -> int:
    """FR-MER-02 and webhook submissions: one notice per active administrator."""
    addresses = administrators()
    for address in addresses:
        notice(address, subject, body)
    return len(addresses)
