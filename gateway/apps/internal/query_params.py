"""Date and bounded-integer query parameters shared by staff API endpoints."""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.common.errors import invalid


def local_zone() -> ZoneInfo:
    return ZoneInfo(settings.DASHBOARD_TIME_ZONE)


def parse_date(value: str, param: str):
    try:
        # Only the calendar date is kept, so no time zone is involved.
        return datetime.strptime(value, "%Y-%m-%d").date()  # noqa: DTZ007
    except ValueError:
        raise invalid("invalid_field", f"'{param}' must be a date like 2026-11-13.",
                      param=param) from None


def bounded_int(value, param, default, low, high):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise invalid("invalid_field", f"'{param}' must be a whole number.", param=param) \
            from None
    return max(low, min(high, number))
