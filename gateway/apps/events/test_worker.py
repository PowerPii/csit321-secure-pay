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
