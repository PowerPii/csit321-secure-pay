"""Public status page: samples, downtime, daily uptime, incidents and GET /status.json."""
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.status import service
from apps.status.models import StatusSample

ALL_UP = {"api": True, "database": True, "worker": True, "network": True, "shop": True}
T0 = datetime(2026, 11, 19, 0, 0, tzinfo=UTC)  # 8 am in Singapore


def samples(start, count, results=ALL_UP, every=service.SAMPLE_EVERY):
    return [(start + every * n, dict(results)) for n in range(count)]


def test_all_up_has_no_downtime():
    rows = samples(T0, 12)
    down = service.downtimes(rows, rows[-1][0] + timedelta(minutes=1))
    assert all(intervals == [] for intervals in down.values())


def test_a_failure_lasts_until_the_next_passing_sample():
    rows = samples(T0, 3) + samples(T0 + timedelta(minutes=15), 2, {**ALL_UP, "network": False}) \
        + samples(T0 + timedelta(minutes=25), 2)
    down = service.downtimes(rows, T0 + timedelta(minutes=31))
    assert down["network"] == [(T0 + timedelta(minutes=15), T0 + timedelta(minutes=25))]
    assert down["worker"] == [] and down["shop"] == []


def test_a_gap_in_samples_is_the_worker_down_and_the_rest_unknown():
    rows = samples(T0, 3, {**ALL_UP, "shop": False}) + samples(T0 + timedelta(hours=1), 2)
    down = service.downtimes(rows, T0 + timedelta(hours=1, minutes=6))
    gap = (T0 + timedelta(minutes=15), T0 + timedelta(hours=1))
    assert down["worker"] == [gap]
    # The shop was failing when the samples stopped: its outage ends there, not an hour later.
    assert down["shop"] == [(T0, T0 + timedelta(minutes=15))]
    up = service._uptime("shop", down, T0, T0 + timedelta(hours=1, minutes=10), T0 + timedelta(hours=2))
    # 15 minutes down out of the 25 minutes that were measured.
    assert up == 40.0


def test_ongoing_outages_have_no_end():
    rows = samples(T0, 2) + samples(T0 + timedelta(minutes=10), 1, {**ALL_UP, "api": False})
    down = service.downtimes(rows, T0 + timedelta(minutes=12))
    assert down["api"] == [(T0 + timedelta(minutes=10), None)]
    stopped = service.downtimes(rows, T0 + timedelta(hours=2))
    assert stopped["worker"] == [(T0 + timedelta(minutes=15), None)]


def test_uptime_never_rounds_a_bad_day_up_to_100():
    rows = samples(T0, 288)
    rows[100] = (rows[100][0], {**ALL_UP, "api": False})
    now = T0 + timedelta(days=1)
    down = service.downtimes(rows, now)
    assert service._uptime("api", down, T0, now, now) == 99.65  # 5 of 1,440 minutes


def test_overall_status():
    up = dict.fromkeys(service.IDS, "operational")
    assert service.overall(up) == "operational"
    assert service.overall({**up, "shop": "outage"}) == "partial_outage"
    assert service.overall({**up, "database": "outage"}) == "major_outage"
    # No recent check is not the same as a passing one (completion audit, 19 Nov 2026).
    assert service.overall({**up, "network": "unknown"}) == "unknown"
    assert service.overall({**up, "network": "unknown", "shop": "outage"}) == "partial_outage"


@pytest.mark.django_db(databases=["default", "vault"])
def test_record_sample_every_five_minutes_and_prunes_old_ones(monkeypatch):
    monkeypatch.setattr(service, "check_now", lambda: dict(ALL_UP))
    old = StatusSample.objects.create(taken_at=T0 - timedelta(days=95), results=ALL_UP)
    assert service.record_sample(now=T0) is not None
    assert not StatusSample.objects.filter(pk=old.pk).exists()
    assert service.record_sample(now=T0 + timedelta(minutes=2)) is None
    assert service.record_sample(now=T0 + timedelta(minutes=5)) is not None
    assert StatusSample.objects.count() == 2


@pytest.mark.django_db(databases=["default", "vault"])
def test_check_now_probes_only_configured_parts(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_answers", lambda url, verify: calls.append(url) or True)
    settings.STATUS_GATEWAY_URL = ""
    settings.STATUS_SHOP_URL = "https://shop.example.test"
    settings.SIMULATOR_URL = "https://sim.example.test/"
    results = service.check_now()
    assert list(results) == ["database", "worker", "network", "shop"]
    assert calls == ["https://sim.example.test/healthz", "https://shop.example.test/healthz"]


def test_a_probe_that_cannot_connect_is_down():
    assert service._answers("http://127.0.0.1:9/healthz", True) is False


@pytest.mark.django_db(databases=["default", "vault"])
def test_status_json(client, settings):
    from apps.events.models import WorkerHeartbeat

    settings.STATUS_NOTICE = "Planned upgrade on Saturday 10 pm SGT."
    now = timezone.now()
    WorkerHeartbeat.objects.create(name="worker", seen_at=now)
    start = now - timedelta(hours=3)
    for taken_at, results in samples(start, 36):
        if start + timedelta(hours=1) <= taken_at < start + timedelta(hours=1, minutes=20):
            results = {**results, "network": False}
        StatusSample.objects.create(taken_at=taken_at, results=results)

    response = client.get("/status.json")
    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "*"
    assert "public" in response["Cache-Control"]
    data = response.json()
    assert data["status"] == "operational"
    assert data["checked_at"] is not None
    assert data["notice"] == "Planned upgrade on Saturday 10 pm SGT."
    assert [c["id"] for c in data["components"]] == service.IDS
    network = next(c for c in data["components"] if c["id"] == "network")
    assert network["status"] == "operational"
    assert len(network["days"]) == 90 and network["days"][0]["uptime"] is None
    assert 0 < network["uptime"] < 100
    [incident] = data["incidents"]
    assert incident["component"] == "network" and incident["minutes"] == 20
    assert incident["ended_at"] is not None
    # Nothing personal or payment related in the reply.
    text = response.content.decode()
    assert "@" not in text and "pay_" not in text


@pytest.mark.django_db(databases=["default", "vault"])
def test_status_json_with_no_samples_yet_and_a_stopped_worker(client):
    data = client.get("/status.json").json()
    assert data["status"] == "partial_outage"
    states = {c["id"]: c["status"] for c in data["components"]}
    assert states == {"api": "operational", "database": "operational", "worker": "outage",
                      "network": "unknown", "shop": "unknown"}
    assert data["measured_since"] is None and data["incidents"] == []


@pytest.mark.django_db(databases=["default", "vault"])
def test_status_json_when_the_database_cannot_be_read(client, monkeypatch):
    from django.db import DatabaseError

    def broken():
        raise DatabaseError("down")

    monkeypatch.setattr(service, "build_status", broken)
    data = client.get("/status.json").json()
    assert data["status"] == "major_outage"
    assert {c["id"]: c["status"] for c in data["components"]}["database"] == "outage"


@pytest.mark.django_db(databases=["default", "vault"])
def test_status_json_when_the_rate_limit_counter_cannot_be_read(client, monkeypatch):
    """The rate limit counts in the database too; losing it must still give the degraded
    answer, not a 500 (completion audit, 19 Nov 2026)."""
    from django.db import DatabaseError

    from apps.common import throttling

    def broken(self, request, view):
        raise DatabaseError("down")

    def no_cache(*args, **kwargs):
        raise DatabaseError("down")

    monkeypatch.setattr(throttling.SimpleRateThrottle, "allow_request", broken)
    monkeypatch.setattr("apps.status.views.cache.get", no_cache)
    response = client.get("/status.json")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "major_outage"
    assert {c["id"]: c["status"] for c in data["components"]}["database"] == "outage"
