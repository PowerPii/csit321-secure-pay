# Secrets

Compose mounts each file here at `/run/secrets/<name>`. Only the `.example` files are committed; real files are git-ignored.

```bash
cd deploy/secrets
for f in *.example; do python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "${f%.example}"; done
# vault_encryption_key must be a Fernet key instead:
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > vault_encryption_key
```
