"""Restore drill (Codex completion audit, 19 Nov 2026, section 4; docs/RECOVERY.md).

A backup taken while a checkout is in flight (card entered, not yet submitted) is restored
into the running local stack. Afterwards:

* financial history is all there: the payment authorised before the backup is still
  authorised and can still be captured, so the gateway and simulator agree about it;
* a payment made after the backup is gone (the restore really went back in time);
* the vault holds zero rows: the in-flight card never reached the backup;
* the in-flight payment asks for the card again instead of failing or charging, and goes
  through once the card is entered again;
* `manage.py recovery_check` passes.

It REPLACES the local stack's databases, so it only runs when asked:

    RECOVERY_DRILL=1 .venv-it/bin/pytest tests/integration/test_recovery_drill.py -v

Never against the public server: restore.sh refuses compose.prod.yaml without
--replace-live-data, and this test always uses deploy/compose.yaml.
"""
import os
import subprocess
import time

import pytest

from conftest import (APPROVE, APPROVE_2, DECLINE, ROOT, create_payment, pay, session_id,
                      wait_for_status)

COMPOSE = ["docker", "compose", "-f", str(ROOT / "deploy" / "compose.yaml")]
CARD = {"expiry_month": 12, "expiry_year": 2030, "cvc": "123", "privacy_consent": True}

pytestmark = pytest.mark.skipif(os.environ.get("RECOVERY_DRILL") != "1",
                                reason="replaces the local databases; set RECOVERY_DRILL=1")


def sql(query: str) -> str:
    out = subprocess.run([*COMPOSE, "exec", "-T", "db", "psql", "-U", "postgres", "-d", "gateway",
                          "-qAt", "-c", query], check=True, capture_output=True, text=True)
    return out.stdout.strip()


def script(path: str, *args, env: dict) -> str:
    result = subprocess.run(["bash", str(ROOT / path), *args], capture_output=True, text=True,
                            env={**os.environ, "COMPOSE_FILE": str(ROOT / "deploy" / "compose.yaml"),
                                 **env}, timeout=600)
    assert result.returncode == 0, f"{path} failed:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def test_restore_during_an_in_flight_checkout(browser_factory, merchant_api, tmp_path):
    backups = {"BACKUP_DIR": str(tmp_path / "backups")}

    # Before the backup: one finished payment, one checkout with its card entered.
    done = create_payment(merchant_api)
    assert pay(browser_factory(), done, APPROVE)["status"] == "authorised"
    in_flight = create_payment(merchant_api)
    browser = browser_factory()
    base = f"/checkout/{session_id(in_flight)}"
    entered = browser.post(f"{base}/card", json={"number": APPROVE_2, **CARD})
    assert entered.status_code == 200, entered.text
    assert int(sql("SELECT count(*) FROM vault.vault_storedcard")) >= 1  # the card is held now
    payments_before = int(sql("SELECT count(*) FROM payments_payment"))

    out = script("deploy/backup/backup.sh", env=backups)
    folder = out.strip().rsplit(" ", 1)[-1]
    assert os.path.isfile(os.path.join(folder, "MANIFEST")), out

    # After the backup: a payment that the restore must take away again.
    later = create_payment(merchant_api)
    pay(browser_factory(), later, DECLINE)

    started = time.time()
    out = script("deploy/backup/restore.sh", folder, env=backups)
    print(f"restore took {time.time() - started:.0f} s")
    assert "vault rows: 0" in out, out

    # Financial history is back, the later payment is gone, and no card came back.
    assert int(sql("SELECT count(*) FROM payments_payment")) == payments_before
    assert merchant_api.get(f"/v1/payments/{done['id']}").json()["status"] == "authorised"
    assert merchant_api.get(f"/v1/payments/{later['id']}").status_code == 404
    assert sql("SELECT count(*) FROM vault.vault_storedcard") == "0"

    # The in-flight payment asks for the card again, then goes through exactly once.
    retry = browser.post(f"{base}/submit", json={}, timeout=30)
    assert retry.status_code == 400 and retry.json()["error"]["code"] == "card_required", retry.text
    assert merchant_api.get(f"/v1/payments/{in_flight['id']}").json()["status"] == "created"
    again = pay(browser, in_flight, APPROVE_2)
    assert again["status"] == "authorised", again
    payment = wait_for_status(merchant_api, in_flight["id"], {"authorised"}, timeout=10)
    assert payment["status"] == "authorised"

    # The payment from before the backup still settles with the simulator.
    captured = merchant_api.post(f"/v1/payments/{done['id']}/capture", json={},
                                 headers={"Idempotency-Key": f"drill-{done['id']}"})
    assert captured.status_code == 200 and captured.json()["status"] == "captured", captured.text

    check = subprocess.run([*COMPOSE, "exec", "-T", "gateway", "python", "manage.py",
                            "recovery_check", "--payment", done["id"], "--payment",
                            in_flight["id"]], capture_output=True, text=True)
    assert check.returncode == 0, check.stdout + check.stderr
