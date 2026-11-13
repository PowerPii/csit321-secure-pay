from datetime import UTC, datetime


def rfc3339(dt: datetime | None) -> str | None:
    """UTC timestamp with a `Z` suffix and whole seconds, as the contract shows."""
    if dt is None:
        return None
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
