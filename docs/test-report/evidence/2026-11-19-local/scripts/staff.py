"""Tiny staff client for the disposable local stack: password + TOTP sign-in over HTTPS."""
import base64, hashlib, hmac, struct, time, httpx
BASE = "https://gateway.localhost"
CA = "/tmp/claude-0/caddy-root.crt"

def totp(secret_b32, t=None):
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    counter = int((t or time.time()) // 30)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000)

def sign_in(email, password, secret_file="/tmp/claude-0/ev/totp.secret"):
    c = httpx.Client(base_url=BASE, verify=CA, timeout=30, trust_env=False)
    c.get("/internal/me")
    h = lambda: {"X-CSRFToken": c.cookies.get("csrftoken"), "Referer": BASE + "/dashboard/"}
    r = c.post("/internal/auth/login", json={"email": email, "password": password}, headers=h())
    r.raise_for_status()
    setup = r.json().get("setup")
    if setup:
        open(secret_file, "w").write(setup["secret"])
    secret = open(secret_file).read().strip()
    r = c.post("/internal/auth/totp", json={"code": totp(secret)}, headers=h())
    if r.status_code != 200:  # code already used in this 30 s window
        time.sleep(31)
        r = c.post("/internal/auth/totp", json={"code": totp(secret)}, headers=h())
    r.raise_for_status()
    c.headers.update(h())
    return c
