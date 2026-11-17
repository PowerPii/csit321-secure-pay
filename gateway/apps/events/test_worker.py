"""The worker loop runs every job and survives a failing one."""
import pytest

from apps.events.management.commands import run_worker

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


def test_one_pass_runs_every_job(monkeypatch):
    ran = []
    jobs = [lambda name=name: ran.append(name) for name in ("a", "b")]
    monkeypatch.setattr(run_worker, "JOBS", jobs)
    run_worker.run_pass()
    assert ran == ["a", "b"]


def test_a_failing_job_does_not_stop_the_others(monkeypatch, caplog):
    ran = []

    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(run_worker, "JOBS", [broken, lambda: ran.append("next")])
    run_worker.run_pass()
    assert ran == ["next"] and "boom" in caplog.text


def test_real_jobs_run_on_an_empty_database():
    run_worker.run_pass()


def test_a_pass_records_the_heartbeat(monkeypatch):
    from apps.events.models import WorkerHeartbeat

    monkeypatch.setattr(run_worker, "JOBS", [])
    monkeypatch.setattr(run_worker, "close_old_connections", lambda: None)
    monkeypatch.setattr(run_worker, "_last_beat", 0.0)
    run_worker.run_pass()
    first = WorkerHeartbeat.objects.get(name="worker").seen_at
    run_worker.beat()  # within 15 s: no extra write
    assert WorkerHeartbeat.objects.get(name="worker").seen_at == first
    run_worker.beat(force=True)
    assert WorkerHeartbeat.objects.get(name="worker").seen_at > first
