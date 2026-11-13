"""The client's IP address as screening sees it.

Behind Caddy, REMOTE_ADDR is the proxy, so the address is read from X-Forwarded-For, counting
`settings.TRUSTED_PROXY_HOPS` entries from the right (entries further left were written by
the client and cannot be trusted). With no trusted proxy, REMOTE_ADDR is used.
"""
import ipaddress

from django.conf import settings


def client_ip(request) -> str | None:
    hops = settings.TRUSTED_PROXY_HOPS
    candidate = request.META.get("REMOTE_ADDR")
    if hops > 0:
        chain = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
                 if p.strip()]
        if len(chain) >= hops:
            candidate = chain[-hops]
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None
