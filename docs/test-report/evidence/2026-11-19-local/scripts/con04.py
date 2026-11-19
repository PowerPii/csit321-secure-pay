"""NFR-CON-04 / M-CON-04: 11-character passwords refused on every sign-up path; 12+ accepted;
then aggregate checks on the stored hashes (no hash is printed)."""
import httpx, json, secrets, subprocess
c = httpx.Client(base_url="https://gateway.localhost", verify="/tmp/claude-0/caddy-root.crt", trust_env=False, timeout=30)
H = {"Origin": "https://gateway.localhost", "Referer": "https://gateway.localhost/"}
out = {}
def cust(email, pw):
    r = c.post("/customer/register", json={"full_name": "Evidence Customer", "email": email, "password": pw, "privacy_consent": True}, headers=H)
    return r.status_code, r.json().get("error", {}).get("code")
out["customer sign-up, 11 chars (Abcdefgh12!)"] = cust("short-pw@example.test", "Abcdefgh12!")
out["customer sign-up, 12 chars"] = cust("ok12-pw@example.test", "Ev1d-" + secrets.token_hex(3) + "x")
for i in range(4):
    cust(f"evidence-cust{i}@example.test", "Evid3nce-" + secrets.token_hex(4))
# merchant self-registration (D7) needs the CSRF cookie
s = httpx.Client(base_url="https://gateway.localhost", verify="/tmp/claude-0/caddy-root.crt", trust_env=False, timeout=30)
s.get("/internal/me")
SH = {"X-CSRFToken": s.cookies.get("csrftoken"), "Referer": "https://gateway.localhost/dashboard/"}
def merch(email, pw, uen):
    r = s.post("/internal/register", json={"business_name": "Evidence Pte Ltd", "registration_number": uen, "website": "https://example.test",
               "contact_name": "Evidence Contact", "email": email, "password": pw, "confirmed": True}, headers=SH)
    return r.status_code, (r.json().get("error") or {}).get("code") if r.headers.get("content-type", "").startswith("application/json") else r.text[:80]
out["merchant registration (D7), 11 chars"] = merch("short-merchant@example.test", "Abcdefgh12!", "202699001K")
out["merchant registration (D7), 12 chars"] = merch("ok-merchant@example.test", "Ev1d-" + secrets.token_hex(3) + "x", "202699002K")
P = ["docker", "compose", "-p", "nfr", "-f", "deploy/compose.yaml", "exec", "-T"]
r = subprocess.run(P + ["gateway", "sh", "-c", "printf 'Abcdefgh12!' > /tmp/pw11 && python manage.py create_staff short-staff@example.test --role fraud_analyst --password-file /tmp/pw11; echo exit=$?"], capture_output=True, text=True)
out["create_staff command, 11 chars"] = (r.stdout + r.stderr).strip().splitlines()[-2:]
sql = r"""
SELECT 'staff (auth_user)', count(*), count(*) FILTER (WHERE password LIKE 'argon2$argon2id$%'),
       count(DISTINCT split_part(password, '$', 5)), count(*) FILTER (WHERE password LIKE '!%' OR password = ''),
       min(split_part(password, '$', 3) || ' ' || split_part(password, '$', 4)), max(split_part(password, '$', 3) || ' ' || split_part(password, '$', 4))
  FROM auth_user
UNION ALL
SELECT 'customer (customers_customeraccount)', count(*), count(*) FILTER (WHERE password LIKE 'argon2$argon2id$%'),
       count(DISTINCT split_part(password, '$', 5)), count(*) FILTER (WHERE password LIKE '!%' OR password = ''),
       min(split_part(password, '$', 3) || ' ' || split_part(password, '$', 4)), max(split_part(password, '$', 3) || ' ' || split_part(password, '$', 4))
  FROM customers_customeraccount;"""
r = subprocess.run(P + ["db", "psql", "-U", "postgres", "-d", "gateway", "-At", "-F", " | ", "-c", sql], capture_output=True, text=True)
out["hash aggregate: table | rows | argon2id rows | distinct salts | unusable | version+params (min) | (max)"] = r.stdout.strip().splitlines()
print(json.dumps(out, indent=1))
