"""Rate-limit counters stay exact when several workers count the same key at once
(Codex release review, 18 Nov 2026: DRF's read-modify-write lost updates)."""
import threading

import pytest
from django.core.cache import cache
from django.db import connections
from rest_framework.test import APIRequestFactory

from apps.common import throttling

LIMIT = 5
PARALLEL = 24


class FivePerMinute(throttling.SimpleRateThrottle):
    scope = "test"
    rate = f"{LIMIT}/min"

    def get_rate(self):
        return self.rate

    def get_cache_key(self, request, view):
        return "throttle_test_shared_key"


class SlowCache:
    """The real database cache, with a pause between reading a history and writing it back,
    so every unlocked request would read the history before any other writes."""

    def __init__(self, barrier):
        self.barrier = barrier

    def get(self, key, default=None):
        value = cache.get(key, default)
        try:
            self.barrier.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        return value

    def set(self, *args, **kwargs):
        return cache.set(*args, **kwargs)


def _run_in_parallel(throttle_class, barrier):
    request = APIRequestFactory().get("/", REMOTE_ADDR="203.0.113.9")
    allowed = []

    def one_request():
        throttle = throttle_class()
        throttle.cache = SlowCache(barrier)
        try:
            allowed.append(throttle.allow_request(request, None))
        finally:
            connections.close_all()  # each thread opened its own database connection

    threads = [threading.Thread(target=one_request) for _ in range(PARALLEL)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return allowed


@pytest.mark.django_db(transaction=True)
def test_parallel_requests_for_one_key_never_pass_the_limit():
    allowed = _run_in_parallel(FivePerMinute, threading.Barrier(PARALLEL))
    assert len(allowed) == PARALLEL
    assert allowed.count(True) == LIMIT
    assert len(cache.get("throttle_test_shared_key")) == LIMIT


@pytest.mark.django_db(transaction=True)
def test_without_the_lock_the_same_burst_gets_through():
    """Shows what the lock prevents: DRF's own class lets the whole burst in."""
    from rest_framework.throttling import SimpleRateThrottle as DrfSimpleRateThrottle

    class Unlocked(DrfSimpleRateThrottle):
        scope = "test"
        rate = f"{LIMIT}/min"
        get_rate = FivePerMinute.get_rate
        get_cache_key = FivePerMinute.get_cache_key

    allowed = _run_in_parallel(Unlocked, threading.Barrier(PARALLEL))
    assert allowed.count(True) > LIMIT


def test_every_view_uses_the_locked_throttles():
    from django.conf import settings

    from apps.common.views import PublicJSONView
    from apps.customers import views as customer_views
    from apps.internal.views import accounts, auth
    from apps.merchants.api import MerchantAPIView

    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] == [
        "apps.common.throttling.AnonRateThrottle"]
    views = [PublicJSONView, MerchantAPIView, *vars(customer_views).values(),
             *vars(accounts).values(), *vars(auth).values()]
    for view in views:
        for throttle in getattr(view, "throttle_classes", None) or []:
            assert issubclass(throttle, throttling.SimpleRateThrottle), (view, throttle)


def test_scoped_throttle_still_reads_its_rate_from_the_view():
    class View:
        throttle_scope = "customer_auth"

    throttle = throttling.ScopedRateThrottle()
    throttle.get_cache_key = lambda request, view: None  # no database needed for this check
    assert throttle.allow_request(APIRequestFactory().get("/"), View())
    expected = throttle.parse_rate(throttle.THROTTLE_RATES["customer_auth"])
    assert (throttle.num_requests, throttle.duration) == expected
