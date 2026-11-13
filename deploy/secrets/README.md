# Secrets

Compose mounts each file here at `/run/secrets/<name>`. Only the `.example` files are committed; real files are git-ignored.

```bash
cd deploy/secrets
for f in *.example; do python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "${f%.example}"; done
# vault_encryption_key and field_encryption_key must be Fernet keys instead:
for f in vault_encryption_key field_encryption_key; do
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > "$f"
done
```

| File | Used by | What |
| --- | --- | --- |
| `simulator_api_key` | gateway, simulator | Bearer key the gateway sends to the simulator (any random string) |
| `simulator_signing_secret` | gateway, simulator | Signs the simulator's replies and notifications (any random string) |
| `simulator_test_control_key` | simulator, test runner | Opens the simulator's `/sim/faults` test controls (SIMULATOR-CONTRACT.md section 8). Never given to the gateway. `tests/integration` reads it from this file. |
| `securepay_api_key`, `securepay_signing_secret` | merchant | The demo shop's SecurePay API key and signing secret. Random placeholders at first; replace them with the values `create_merchant` prints (see the main README), then restart `merchant`. |
