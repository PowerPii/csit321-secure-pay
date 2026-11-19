"""After the crash run: every authorise the gateway recorded vs every authorise the simulator
recorded, matched by operation_id (SIMULATOR-CONTRACT.md section 2)."""
import json, subprocess, sys
P = ["docker", "compose", "-p", "nfr", "-f", "deploy/compose.yaml", "exec", "-T", "db", "psql", "-U", "postgres", "-At", "-F", "|"]
since = sys.argv[1]  # ISO time the load started
def q(db, s): return [l.split("|") for l in subprocess.run(P + ["-d", db, "-c", s], capture_output=True, text=True).stdout.strip().splitlines() if l]
gw = q("gateway", f"""SELECT o.public_id, o.status, p.public_id, p.status, o.reconciliation_checks, o.escalated_at IS NOT NULL
  FROM payments_operation o JOIN payments_payment p ON p.id = o.payment_id
  WHERE o.type = 'authorise' AND p.created_at >= '{since}'""")
pays = q("gateway", f"SELECT status, count(*) FROM payments_payment WHERE created_at >= '{since}' GROUP BY 1 ORDER BY 2 DESC")
sim = q("simulator", f"""SELECT operation_id, status, payment_id FROM operations_operationrecord
  WHERE type = 'authorise' AND recorded_at >= '{since}'::timestamptz - interval '5 seconds'""")
g = {r[0]: r for r in gw}; s = {r[0]: r for r in sim}
ok_gw = {"succeeded"}; ok_sim = {"approved"}
out = {
 "payments created in the run, by status": {k: int(v) for k, v in pays},
 "gateway authorise operations": len(g),
 "gateway authorise operations by status": {st: sum(1 for r in gw if r[1] == st) for st in sorted({r[1] for r in gw})},
 "simulator authorise records": len(s),
 "simulator records by status": {st: sum(1 for r in sim if r[1] == st) for st in sorted({r[1] for r in sim})},
 "on simulator, missing on gateway": sorted(set(s) - set(g)),
 "approved on simulator but not succeeded on gateway": [k for k in s if s[k][1] in ok_sim and g.get(k, [None, None])[1] not in ok_gw],
 "succeeded on gateway but not approved on simulator": [k for k in g if g[k][1] in ok_gw and s.get(k, [None, None])[1] not in ok_sim],
 "payments with more than one succeeded authorise (gateway)": [p for p in {r[2] for r in gw} if sum(1 for r in gw if r[2] == p and r[1] in ok_gw) > 1],
 "payments approved more than once (simulator)": [p for p in {r[2] for r in sim} if sum(1 for r in sim if r[2] == p and r[1] in ok_sim) > 1],
 "gateway operations still unresolved (pending/unknown)": [k for k in g if g[k][1] not in ("succeeded", "failed", "declined", "not_processed")],
 "operations that needed a status check": sum(1 for r in gw if int(r[4]) > 0),
 "operations escalated": sum(1 for r in gw if r[5] == "t"),
}
print(json.dumps(out, indent=1))
