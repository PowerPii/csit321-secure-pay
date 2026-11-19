# Local run of 20 Nov 2026 (release audit before v1.0.0)

| What | Detail |
| --- | --- |
| Revision | `db8cacd` (main after PR #80) |
| Environment | Cloud container (Python 3.12, Node 22, PostgreSQL 16 for the unit suites); for the stack checks, a disposable local copy of the stack from `deploy/compose.yaml` (images built from `db8cacd`, Caddy local CA, synthetic data only, stub model), torn down afterwards. Not the live server. |
| Who | Claude (release audit thread, branch `claude/project-thread-77iawl`); `reviewed_by` left for the team |

| File | What it shows |
| --- | --- |
| `local-ci-scripts.txt` | `.github/ci-python.sh` for gateway, simulator and merchant (ruff, Django checks, migrations check, pytest, pip-audit, bandit) and `.github/ci-frontend.sh` for checkout, dashboard, website and the SDK (type check, lint, tests, build, npm audit), run locally because the GitHub Actions minutes are used up until 1 Dec. All passed. |
| `integration.txt` | `pytest tests/integration` on the fresh stack: 11 passed, 1 skipped (the opt-in recovery drill) |
| `recovery-drill.txt` | `RECOVERY_DRILL=1 pytest tests/integration/test_recovery_drill.py`: backup with a checkout in flight, restore, history back, no vault rows, card asked again then paid once, `recovery_check` passes |
| `m-ava-05-backup-verify.txt` | `deploy/backup/backup.sh` then `deploy/backup/verify.sh` on the same stack: MANIFEST checksums match, all three dumps restore, vault table present and empty |
| `m-mnt-02.txt` | The gateway's database role is refused on the vault schema |

Not covered here, because it needs the live server: the nightly and weekly cron lines and the
14-day retention of M-AVA-05 (so M-AVA-05 stays pending until someone runs it on the server).
