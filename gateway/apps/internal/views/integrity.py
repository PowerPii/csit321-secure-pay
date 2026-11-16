"""Integrity, encryption keys, self-checks and clean-up for administrators.

* GET  integrity : the page in one call: latest run of each kind, the key report, schedule.
* GET  integrity/runs?kind=&page= : run history, newest first.
* GET  integrity/runs/{id} : one run with its findings.
* POST integrity/run {kind} : run a check or the clean-up now (FR-ADM-09, FR-ADM-15,
  NFR-PRI-01). 409 run_in_progress if the worker is running the same kind.
* POST security/keys/rotate {purpose, code} : rotate a data key after re-entering the
  authenticator code (FR-ADM-14, UC-45). The old key stays for decryption only.
"""
from rest_framework.response import Response

from apps.accounts import signin
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid, not_found
from apps.common.timefmt import rfc3339
from apps.internal.access import ADMIN, StaffAPIView
from apps.internal.views.payments import _int
from apps.security import keyring, maintenance
from apps.security.models import DataKey, MaintenanceRun

PAGE_SIZE = 20


def run_to_dict(run: MaintenanceRun | None, full: bool = True) -> dict | None:
    if run is None:
        return None
    data = {
        "id": run.public_id,
        "kind": run.kind,
        "kind_label": MaintenanceRun.Kind(run.kind).label,
        "outcome": run.outcome,
        "started_at": rfc3339(run.started_at),
        "finished_at": rfc3339(run.finished_at),
        "started_by": run.started_by or None,
    }
    if full:
        data["summary"] = run.summary
    return data


def key_to_dict(row: dict) -> dict:
    return {**row, "created_at": rfc3339(row["created_at"]),
            "retired_at": rfc3339(row["retired_at"]), "rotate_by": rfc3339(row["rotate_by"])}


def overview() -> dict:
    latest = {kind: MaintenanceRun.objects.filter(kind=kind).first()
              for kind in MaintenanceRun.Kind.values}
    schedule = {}
    for kind, run in latest.items():
        every = maintenance.interval(kind)
        schedule[kind] = {"every_hours": int(every.total_seconds() // 3600),
                          "next_at": rfc3339(run.started_at + every) if run else None}
    return {
        "runs": {kind: run_to_dict(run) for kind, run in latest.items()},
        "schedule": schedule,
        "keys": [key_to_dict(k) for k in keyring.report()],
        "key_max_age_days": keyring.max_age_days(),
    }


class IntegrityView(StaffAPIView):
    roles = ADMIN

    def get(self, request):
        return Response(overview())


class IntegrityRunListView(StaffAPIView):
    roles = ADMIN

    def get(self, request):
        runs = MaintenanceRun.objects.all()
        kind = request.query_params.get("kind")
        if kind:
            if kind not in MaintenanceRun.Kind.values:
                raise invalid("invalid_kind", "Choose integrity, self_check or retention.", "kind")
            runs = runs.filter(kind=kind)
        page = _int(request.query_params.get("page"), "page", 1, 1, 10_000)
        count = runs.count()
        rows = runs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        return Response({"object": "list", "count": count, "page": page,
                         "page_size": PAGE_SIZE,
                         "data": [run_to_dict(r, full=False) for r in rows]})


class IntegrityRunDetailView(StaffAPIView):
    roles = ADMIN

    def get(self, request, run_id: str):
        run = MaintenanceRun.objects.filter(public_id=run_id[:32]).first()
        if run is None:
            raise not_found()
        return Response(run_to_dict(run))


class IntegrityRunNowView(StaffAPIView):
    roles = ADMIN

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        kind = body.get("kind")
        if kind not in MaintenanceRun.Kind.values:
            raise invalid("invalid_kind", "Choose integrity, self_check or retention.", "kind")
        run = maintenance.start(kind, started_by=self.staff.public_id)
        if run is None:
            raise ApiError(409, "run_in_progress", "This check is already running. Try again "
                           "in a minute.")
        return Response({"run": run_to_dict(run), **overview()})


class KeyRotateView(StaffAPIView):
    roles = ADMIN

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        purpose = body.get("purpose")
        if purpose not in DataKey.Purpose.values:
            raise invalid("invalid_purpose", "Choose vault or field.", "purpose")
        signin.confirm_with_totp(request._request, self.staff, body.get("code"),
                                 f"rotate_key:{purpose}")
        new, old = keyring.rotate(purpose, self.staff.public_id)
        audit("security.key_rotated", actor_type=AuditEvent.ActorType.STAFF,
              actor_id=self.staff.public_id, target_type="data_key", target_id=new.key_id,
              request_id=request.request_id,
              details={"purpose": purpose, "previous_key": old.key_id if old else None,
                       "previous_key_age_days": keyring.age_days(old) if old else None})
        return Response({"rotated": {"purpose": purpose, "new_key": new.key_id,
                                     "previous_key": old.key_id if old else None},
                         **overview()})
