"""Administrator-set limits (FR-ADM-07, FR-ADM-12) and rate-limit violations (UC-44).

    current() -> Limits          # effective values, cached for CACHE_SECONDS per process
    record_violation(request, source, scope)

`current()` is read by the payment create view (amount limit, checked before screening) and
by the merchant API throttles. A change applies to new requests within CACHE_SECONDS.

A rejected request is a violation. The first one per source per minute is written to the
audit log (a flood must not flood the log), and once a source has
RATE_LIMIT_ALERT_VIOLATIONS violations within RATE_LIMIT_ALERT_WINDOW_MINUTES
administrators get a security alert (grouped, so it only counts up after that).
"""
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit

CACHE_KEY = "security:gateway-limits"
CACHE_SECONDS = 5


@dataclass(frozen=True)
class Limits:
    max_amount_cents: int
    api_key_requests_per_minute: int
    ip_requests_per_minute: int

    def as_dict(self) -> dict:
        return {"max_amount_cents": self.max_amount_cents,
                "api_key_requests_per_minute": self.api_key_requests_per_minute,
                "ip_requests_per_minute": self.ip_requests_per_minute}


def defaults() -> Limits:
    rules = settings.GATEWAY_RULES
    return Limits(rules["MAX_AMOUNT_CENTS"], rules["API_RATE_LIMIT_PER_MINUTE"],
                  rules["IP_RATE_LIMIT_PER_MINUTE"])


def load() -> Limits:
    from apps.security.models import GatewayLimits

    base = defaults()
    row = GatewayLimits.objects.filter(pk=1).first()
    if row is None:
        return base
    return Limits(
        min(row.max_amount_cents or base.max_amount_cents, base.max_amount_cents),
        row.api_key_requests_per_minute or base.api_key_requests_per_minute,
        row.ip_requests_per_minute or base.ip_requests_per_minute,
    )


def current() -> Limits:
    cached = cache.get(CACHE_KEY)
    if cached is None:
        cached = load()
        cache.set(CACHE_KEY, cached, CACHE_SECONDS)
    return cached


def forget() -> None:
    cache.delete(CACHE_KEY)


def record_violation(request, *, source: str, scope: str, merchant_id: str = "",
                     wait: float | None = None) -> None:
    from apps.security.alerts import raise_alert
    from apps.security.models import AlertKind, Severity

    rules = settings.GATEWAY_RULES
    window = rules["RATE_LIMIT_ALERT_WINDOW_MINUTES"] * 60
    if cache.add(f"security:rl-logged:{scope}:{source}", 1, 60):
        audit("security.rate_limited", actor_type=AuditEvent.ActorType.SYSTEM,
              actor_id="throttle", merchant_id=merchant_id, target_type=scope,
              target_id=source[:32], request_id=getattr(request, "request_id", ""),
              details={"path": request.path[:200], "retry_after": round(wait or 0)})
    key = f"security:rl-count:{scope}:{source}"
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, window)
        count = 1
    if count >= rules["RATE_LIMIT_ALERT_VIOLATIONS"]:
        what = "API key" if scope == "api_key" else "IP address"
        raise_alert(AlertKind.RATE_LIMIT_EXCEEDED, severity=Severity.MEDIUM,
                    source=f"{scope}:{source}"[:80], merchant_id=merchant_id,
                    summary=(f"{what} {source} went over the rate limit {count} times within "
                             f"{rules['RATE_LIMIT_ALERT_WINDOW_MINUTES']} minutes."),
                    details={"violations": count, "path": request.path[:200]})
