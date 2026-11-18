"""Rate-limit counters must be shared by every gunicorn worker (security self-test, Nov 2026)."""
import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.cache.backends.db import DatabaseCache


@pytest.mark.django_db
def test_rate_limit_counters_live_in_the_shared_database_cache():
    assert settings.CACHES["default"]["BACKEND"].endswith("DatabaseCache")
    cache.set("throttle_merchant_api_key_1", [1.0, 2.0], 60)
    # A second cache object stands in for another worker process: it sees the same history.
    other_worker = DatabaseCache(settings.CACHES["default"]["LOCATION"], {})
    assert other_worker.get("throttle_merchant_api_key_1") == [1.0, 2.0]
