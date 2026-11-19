"""NFR-ENC-02 / M-ENC-02 on the disposable stack: encrypted while held, gone after submission
and after expiry, and a backup taken while a card is held restores with zero vault rows."""
import json, os, re, subprocess, sys, time, uuid, httpx
CA = "/tmp/claude-0/caddy-root.crt"
P = ["docker", "compose", "-p", "nfr", "-f", "deploy/compose.yaml"]
key = open("deploy/secrets/securepay_api_key").read().strip()
api = httpx.Client(base_url="https://gateway.localhost", verify=CA, trust_env=False, timeout=30, headers={"Authorization": f"Bearer {key}"})
br = httpx.Client(base_url="https://gateway.localhost", verify=CA, trust_env=False, timeout=60)
cards = [l.strip() for l in open("/tmp/claude-0/ev/cards.txt") if l.strip()]
def sql(q, user="postgres"):
    r = subprocess.run(P + ["exec", "-T", "db", "psql", "-U", user, "-d", "gateway", "-At", "-c", q], capture_output=True, text=True)
    return (r.stdout.strip() or r.stderr.strip().splitlines()[0])
def shell(code):
    r = subprocess.run(P + ["exec", "-T", "gateway", "python", "manage.py", "shell", "-c", code], capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()
def new_payment(amount=2590):
    body = {"amount": amount, "currency": "SGD", "order_reference": f"ENC-{uuid.uuid4().hex[:8]}",
            "return_url": "https://shop.localhost/orders/1/return", "customer_email": f"enc-{uuid.uuid4().hex[:6]}@example.com"}
    p = api.post("/v1/payments", json=body, headers={"Idempotency-Key": str(uuid.uuid4())}).json()
    return p, re.search(r"(cs_[0-9A-Za-z]{24})", p["checkout_url"]).group(1)
def vault_card(cs, card):
    r = br.post(f"/checkout/{cs}/card", json={"number": card, "expiry_month": 12, "expiry_year": 2030, "cvc": "123", "privacy_consent": True})
    assert r.status_code == 200, r.text
def token_of(pid):
    return sql(f"SELECT card_token FROM payments_payment WHERE public_id='{pid}'")
def held(tok):
    return sql(f"SELECT count(*) FROM vault.vault_storedcard WHERE token='{tok}'")
out = {}
# A. held -> encrypted; submitted -> gone
p1, cs1 = new_payment(); vault_card(cs1, cards[0]); t1 = token_of(p1["id"])
digits = cards[0]
out["A1 card held after entry (vault rows for token)"] = held(t1)
out["A2 stored ciphertext format / length / contains card digits or last4 in clear"] = sql(
    f"SELECT split_part(ciphertext,'.',1) || '.', length(ciphertext), ciphertext LIKE '%{digits}%', ciphertext LIKE '%{digits[-4:]}%' "
    f"FROM vault.vault_storedcard WHERE token='{t1}'")
out["A3 AES-256-GCM: decrypts with the vault key + token; one changed byte or another row's token fails"] = shell(f"""
from apps.vault import service as v
from apps.vault.models import StoredCard
from apps.security import keyring
import base64
c = StoredCard.objects.using('vault').get(token='{t1}')
pt = v._decrypt(c.ciphertext, c.token)
print('decrypts:', b'"number"' in pt or b'number' in pt, '| matches entered card:', '{digits}'.encode() in pt)
head, b64 = c.ciphertext.rsplit('.', 1)
raw = bytearray(base64.b64decode(b64)); raw[20] ^= 1
for label, value, tok in [('tampered byte', head + '.' + base64.b64encode(bytes(raw)).decode(), c.token), ('wrong token (AAD)', c.ciphertext, 'tok_' + 'x'*24)]:
    try:
        v._decrypt(value, tok); print(label, 'DECRYPTED (bad)')
    except Exception as e:
        print(label, 'refused:', type(e).__name__)
print('nonce+tag overhead bytes:', len(base64.b64decode(b64)) - len(pt))
""")
r = br.post(f"/checkout/{cs1}/submit", json={}); out["A4 submit"] = [r.status_code, r.json().get("status")]
time.sleep(2)
out["A5 vault rows for that token after submission"] = held(t1)
# B. held, then the checkout hour passes (moved forward in this disposable database) -> worker discards it
p2, cs2 = new_payment(); vault_card(cs2, cards[1]); t2 = token_of(p2["id"])
out["B1 card held"] = held(t2)
sql(f"UPDATE payments_payment SET checkout_expires_at = now() - interval '1 minute' WHERE public_id='{p2['id']}'")
for i in range(120):
    if held(t2) == "0": break
    time.sleep(1)
out["B2 seconds until the worker removed it after expiry"] = i
out["B3 vault rows after expiry / payment status"] = [held(t2), api.get(f"/v1/payments/{p2['id']}").json()["status"]]
# C. backup while a card is held, restore into scratch databases
p3, cs3 = new_payment(); vault_card(cs3, cards[2]); t3 = token_of(p3["id"])
out["C1 vault rows (all) at backup time"] = sql("SELECT count(*) FROM vault.vault_storedcard")
bdir = "/tmp/claude-0/ev/backups"
r = subprocess.run(["bash", "deploy/backup/backup.sh"], env={**os.environ, "COMPOSE_FILE": "deploy/compose.yaml", "COMPOSE_PROJECT_NAME": "nfr", "BACKUP_DIR": bdir}, capture_output=True, text=True)
out["C2 backup.sh"] = (r.stdout + r.stderr).strip().splitlines()[-1:]
latest = sorted(os.listdir(bdir))[-1]
dump = open(f"{bdir}/{latest}/gateway.dump", "rb").read()
plain = subprocess.run(P + ["exec", "-T", "db", "pg_restore", "-f", "-"], input=dump, capture_output=True).stdout.decode()
out["C3 gateway.dump as plain SQL (pg_restore -f -): bytes / held card's digits found / vault COPY blocks"] = [
    len(plain), plain.count(digits), plain.count("COPY vault.")]
lst = subprocess.run(P + ["exec", "-T", "db", "pg_restore", "-l"], input=dump, capture_output=True).stdout.decode()
out["C4 pg_restore -l: vault entries (TABLE / TABLE DATA)"] = [len([l for l in lst.splitlines() if "vault_storedcard" in l and " TABLE " in l and "DATA" not in l]),
                                                         len([l for l in lst.splitlines() if "TABLE DATA vault" in l])]
subprocess.run(P + ["exec", "-T", "db", "psql", "-U", "postgres", "-c", "DROP DATABASE IF EXISTS restore_check"], capture_output=True)
subprocess.run(P + ["exec", "-T", "db", "psql", "-U", "postgres", "-c", "CREATE DATABASE restore_check"], capture_output=True)
rr = subprocess.run(P + ["exec", "-T", "db", "pg_restore", "-U", "postgres", "-d", "restore_check", "--no-owner"], input=dump, capture_output=True)
q = lambda s: subprocess.run(P + ["exec", "-T", "db", "psql", "-U", "postgres", "-d", "restore_check", "-At", "-c", s], capture_output=True, text=True).stdout.strip()
out["C5 restored: vault table exists / rows / payments restored / held payment's token still on its payment row"] = [
    q("SELECT to_regclass('vault.vault_storedcard') IS NOT NULL"), q("SELECT count(*) FROM vault.vault_storedcard"),
    q("SELECT count(*) FROM payments_payment"), q(f"SELECT card_token <> '' FROM payments_payment WHERE public_id='{p3['id']}'")]
subprocess.run(P + ["exec", "-T", "db", "psql", "-U", "postgres", "-c", "DROP DATABASE restore_check"], capture_output=True)
# D. the gateway's own role cannot read the vault; expired rows; integrity self-check
out["D1 gateway role reads vault"] = sql("SELECT count(*) FROM vault.vault_storedcard", user="gateway")
out["D2 vault rows now / expired / for submitted payments"] = [sql("SELECT count(*) FROM vault.vault_storedcard"),
    sql("SELECT count(*) FROM vault.vault_storedcard WHERE expires_at < now()"),
    sql("SELECT count(*) FROM vault.vault_storedcard v JOIN payments_payment p ON p.card_token = v.token WHERE p.submitted_at IS NOT NULL")]
out["_ids"] = [p1["id"], p2["id"], p3["id"]]
print(json.dumps(out, indent=1))
