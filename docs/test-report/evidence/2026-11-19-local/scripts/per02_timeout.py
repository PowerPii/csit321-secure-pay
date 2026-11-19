"""PER-02 timeout branch, production settings (DEBUG off): hold a lock on the risk-list table the
rules read, so the screening query waits; the 500 ms statement_timeout must cut it off and the
payment must be blocked as screening_unavailable. Then a control payment after the lock ends."""
import json, re, subprocess, time, uuid, httpx
CA = "/tmp/claude-0/caddy-root.crt"
P = ["docker", "compose", "-p", "nfr", "-f", "deploy/compose.yaml"]
key = open("deploy/secrets/securepay_api_key").read().strip()
api = httpx.Client(base_url="https://gateway.localhost", verify=CA, trust_env=False, timeout=30, headers={"Authorization": f"Bearer {key}"})
cards = [l.strip() for l in open("/tmp/claude-0/ev/cards2.txt") if l.strip()]
def pay(card):
    br = httpx.Client(base_url="https://gateway.localhost", verify=CA, trust_env=False, timeout=30)
    body = {"amount": 3990, "currency": "SGD", "order_reference": f"TMO-{uuid.uuid4().hex[:6]}",
            "return_url": "https://shop.localhost/orders/1/return", "customer_email": f"tmo-{uuid.uuid4().hex[:6]}@example.com"}
    p = api.post("/v1/payments", json=body, headers={"Idempotency-Key": str(uuid.uuid4())}).json()
    cs = re.search(r"(cs_[0-9A-Za-z]{24})", p["checkout_url"]).group(1)
    assert br.post(f"/checkout/{cs}/card", json={"number": card, "expiry_month": 12, "expiry_year": 2030, "cvc": "123", "privacy_consent": True}).status_code == 200
    t = time.perf_counter(); r = br.post(f"/checkout/{cs}/submit", json={}); ms = (time.perf_counter() - t) * 1000
    v = api.get(f"/v1/payments/{p['id']}").json()
    return {"payment": p["id"], "submit_http": r.status_code, "submit_ms": round(ms), "status": v["status"],
            "reason": v.get("outcome_reason") or v.get("failure_reason") or (v.get("outcome") or {}).get("reason")}
locker = subprocess.Popen(P + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "gateway", "-c",
    "BEGIN; LOCK TABLE risk_risklistentry IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(12); COMMIT;"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)
out = {"while the risk list is locked (3 payments)": [pay(c) for c in cards[:3]]}
locker.wait()
out["control, lock released"] = pay(cards[3])
ids = [x["payment"] for x in out["while the risk list is locked (3 payments)"]] + [out["control, lock released"]["payment"]]
sql = ("SELECT p.public_id, e.outcome, e.model_version, e.elapsed_ms FROM risk_screeningevent e JOIN payments_payment p ON p.id = e.payment_id "
       "WHERE p.public_id IN (" + ",".join(f"'{i}'" for i in ids) + ")")
cols = subprocess.run(P + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "gateway", "-At", "-c",
    "SELECT column_name FROM information_schema.columns WHERE table_name='risk_screeningevent'"], capture_output=True, text=True).stdout.split()
out["screening event columns"] = cols
print(json.dumps(out, indent=1))
