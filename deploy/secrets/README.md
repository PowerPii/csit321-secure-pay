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
