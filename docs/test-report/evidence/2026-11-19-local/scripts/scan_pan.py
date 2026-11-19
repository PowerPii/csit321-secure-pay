"""NFR-CON-02 / M-CON-02: look for full card numbers (13-19 digits, Luhn-valid) in every place
a card number could leak after a full synthetic run. Prints counts per location only."""
import json, re, subprocess, sys, httpx
sys.path.insert(0, "/tmp/claude-0/ev")
from staff import sign_in, CA
P = ["docker", "compose", "-p", "nfr", "-f", "deploy/compose.yaml", "-f", "/tmp/claude-0/override.yaml"]
PAN = re.compile(r"(?<![0-9A-Za-z])(?:\d[ -]?){12,18}\d(?![0-9A-Za-z])")
def luhn(d):
    s = 0
    for i, c in enumerate(reversed(d)):
        n = int(c)
        if i % 2: n = n * 2 - 9 if n > 4 else n * 2
        s += n
    return s % 10 == 0
TEST_CARDS = set()
EXACT = ["4000000000000002", "4000000000000101", "4000000000000119", "4000000000000127",
         "4242424242424242", "5555555555554444"]  # every card number tests/integration pays with
def exact(text):
    flat = re.sub(r"[ -]", "", text)
    return sum(flat.count(n) for n in EXACT)
FALSE_POS = {"decimal fraction": 0, "MIME boundary / Message-ID": 0}
def hits(text):
    out = []
    for m in PAN.finditer(text):
        d = re.sub(r"\D", "", m.group())
        if not (13 <= len(d) <= 19 and luhn(d)): continue
        before = text[max(0, m.start() - 1):m.start()]
        if before == ".": FALSE_POS["decimal fraction"] += 1; continue
        if before in ("=", "_") or text[max(0, m.start() - 12):m.start()].endswith((".1.", "<")):
            FALSE_POS["MIME boundary / Message-ID"] += 1; continue
        out.append(d)
    return out
def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw).stdout
results = {}
def record(name, text, note=""):
    h = hits(text)
    results[name] = {"bytes": len(text), "luhn_valid_numbers": len(h), "exact_test_card_matches": exact(text),
                     "distinct": len(set(h)),
                     "known_test_cards": len([x for x in set(h) if x[:6] in ("400000", "424242", "555555", "411111", "510510", "378282", "601111")]),
                     "note": note}
    if h:
        results[name]["first_6_last_4_of_hits"] = sorted({x[:6] + "..." + x[-4:] for x in h})[:10]

# 1. container logs, every service
for svc in ["gateway", "gateway-worker", "simulator", "merchant", "caddy", "mailpit", "db"]:
    record(f"logs:{svc}", sh(P + ["logs", "--no-color", svc]))
# 2. database dumps (data only). Gateway without the vault schema (the vault holds encrypted
#    card data by design, checked separately under NFR-ENC-02).
dump = lambda db, user, extra=[]: sh(P + ["exec", "-T", "db", "pg_dump", "-U", "postgres", "-d", db, "--data-only", *extra])
record("db:gateway (all schemas except vault)", dump("gateway", "postgres", ["--exclude-schema=vault"]))
record("db:merchant (demo shop, incl. received webhooks)", dump("merchant", "postgres"))
record("db:simulator (the simulated bank)", dump("simulator", "postgres"),
       "The simulator plays the card network and issuer; outside the gateway, shown for completeness.")
# 3. emails captured by Mailpit (headers + text + HTML)
mail = httpx.Client(base_url="https://mail.localhost", verify=CA, trust_env=False, timeout=30)
msgs = mail.get("/api/v1/messages", params={"limit": 1000}).json()["messages"]
alltext = ""
for m in msgs:
    alltext += mail.get(f"/api/v1/message/{m['ID']}/raw").text
record(f"emails:mailpit ({len(msgs)} messages, raw source)", alltext)
# 4 + 5. staff dashboard and merchant API: every page of every list, every detail
c = sign_in("evidence-admin@example.test", open("/tmp/claude-0/evidence-admin.pw").read().strip())
def pages(path, **params):
    out, page = [], 1
    while True:
        j = c.get(path, params={"page": page, "page_size": 100, **params}).json()
        out.append(j); data = j.get("data", [])
        if not data or page * j.get("page_size", 100) >= j.get("count", 0): return out
        page += 1
pay_pages = pages("/internal/payments")
pay_ids = [p["id"] for j in pay_pages for p in j["data"]]
t = json.dumps(pay_pages)
for pid in pay_ids:
    t += c.get(f"/internal/payments/{pid}").text + c.get(f"/internal/payments/{pid}/refunds").text
record(f"dashboard:payments ({len(pay_ids)} payments, list + detail + refunds)", t)
key = open("deploy/secrets/securepay_api_key").read().strip()
api = httpx.Client(base_url="https://gateway.localhost", verify=CA, trust_env=False, timeout=30,
                   headers={"Authorization": f"Bearer {key}"})
t = ""; n = 0
for pid in pay_ids:
    r = api.get(f"/v1/payments/{pid}")
    if r.status_code == 200:
        n += 1; t += r.text + api.get(f"/v1/payments/{pid}/refunds").text
record(f"api:/v1/payments/<id> + refunds ({n} payments of the demo shop)", t)
record("export:fraud report CSV (/internal/reports/fraud/export)", c.get("/internal/reports/fraud/export").text)
record("dashboard:fraud report", c.get("/internal/reports/fraud").text)
aud = pages("/internal/audit")
record(f"dashboard:audit log ({aud[0].get('count')} events)", json.dumps(aud))
wh = pages("/internal/webhooks")
t = json.dumps(wh)
for j in wh:
    for w in j["data"]:
        t += c.get(f"/internal/webhooks/{w.get('id') or w.get('event_id')}").text
record(f"dashboard:webhook delivery log ({wh[0].get('count')} events, bodies sent to the shop)", t)
total = sum(v["luhn_valid_numbers"] for k, v in results.items() if not k.startswith("db:simulator"))
exact_total = sum(v["exact_test_card_matches"] for k, v in results.items() if not k.startswith("db:simulator"))
print(json.dumps({"locations": results, "luhn_hits_in_scope": total, "exact_test_card_matches_in_scope": exact_total,
                  "set_aside_as_not_card_numbers": FALSE_POS}, indent=1))
