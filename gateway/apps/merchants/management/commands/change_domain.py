"""Point merchants' webhook URLs at the server's new domain after a server move (sprint 12).

    python manage.py change_domain --from 35-213-144-96.sslip.io --to securepay-demo.me
    python manage.py change_domain --from ... --to ... --dry-run     # show, change nothing

The demo shop's webhook URL is stored in the gateway database as https://shop.<domain>/...
When the stack moves to a new server or domain (deploy/move-server.sh), that URL must follow,
or orders stay unpaid. This rewrites the host of every webhook URL that is <domain> or ends
in .<domain>, keeping the path, and audits each change. An administrator approved the URL
before (FR-ADM-13); the approval is kept because the receiving shop and path are the same,
and the audit event records the old and new URL so the change can be reviewed.

Payments are never touched: their return URLs belong to past checkouts and are covered by
the payment integrity hash.
"""
from urllib.parse import urlsplit, urlunsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.merchants.models import Merchant


def _clean(domain: str) -> str:
    domain = domain.strip().lower().strip(".")
    if not domain or "/" in domain or ":" in domain or " " in domain:
        raise CommandError(f"Not a domain name: {domain!r} (give e.g. securepay-demo.me)")
    return domain


def moved(url: str, old: str, new: str) -> str | None:
    """The URL with its host moved from old to new, or None if it is not on old."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == old:
        new_host = new
    elif host.endswith("." + old):
        new_host = host[: -len(old)] + new
    else:
        return None
    netloc = new_host + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class Command(BaseCommand):
    help = "Move merchants' webhook URLs from one domain to another after a server move."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="old", required=True, help="Old DOMAIN.")
        parser.add_argument("--to", dest="new", required=True, help="New DOMAIN.")
        parser.add_argument("--dry-run", action="store_true", help="Show the changes only.")

    def handle(self, *args, old, new, dry_run, **options):
        old, new = _clean(old), _clean(new)
        if old == new:
            self.stdout.write("Old and new domain are the same; nothing to do.")
            return
        changed = 0
        with transaction.atomic():
            for shop in (Merchant.objects.select_for_update().exclude(webhook_url="")
                         .order_by("id")):
                url = moved(shop.webhook_url, old, new)
                if url is None:
                    continue
                changed += 1
                self.stdout.write(f"{shop.public_id}  {shop.webhook_url}  ->  {url}")
                if dry_run:
                    continue
                before, shop.webhook_url = shop.webhook_url, url
                shop.save(update_fields=["webhook_url", "updated_at"])
                audit("merchant.webhook_url_moved", actor_type=AuditEvent.ActorType.SYSTEM,
                      actor_id="change_domain", merchant_id=shop.public_id,
                      target_type="merchant", target_id=shop.public_id,
                      details={"from": before, "to": url,
                               "approved": shop.webhook_url_approved})
        verb = "Would move" if dry_run else "Moved"
        self.stdout.write(f"{verb} {changed} webhook URL(s) from {old} to {new}.")
