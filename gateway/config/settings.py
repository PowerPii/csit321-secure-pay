"""
Django settings for the gateway.

Configuration comes from environment variables, and secrets from files
mounted by Docker Compose under /run/secrets (see deploy/secrets/).
Nothing secret is committed to the repository.
"""
import base64
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def secret(name, default=None):
    """Read a Compose secret file, falling back to an env var, then a dev default."""
    path = Path(env("SECRETS_DIR", "/run/secrets")) / name
    if path.exists():
        return path.read_text().strip()
    return env(name.upper(), default)


DEBUG = env("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = secret("django_secret_key", "dev-only-insecure-key" if DEBUG else None)
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "localhost").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.accounts",
    "apps.merchants",
    "apps.checkout",
    "apps.vault",
    "apps.payments",
    "apps.refunds",
    "apps.risk",
    "apps.events",
    "apps.reconciliation",
    "apps.audit",
    "apps.internal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "gateway"),
        "USER": env("POSTGRES_USER", "gateway"),
        "PASSWORD": secret("db_password", "gateway"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "ATOMIC_REQUESTS": False,
    }
}

# The vault uses its own database role so that only the vault module can read card data.
DATABASES["vault"] = {
    **DATABASES["default"],
    "USER": env("VAULT_DB_USER", "vault"),
    "PASSWORD": secret("vault_db_password", "vault"),
}
DATABASE_ROUTERS = ["apps.vault.routers.VaultRouter"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Every service sits behind Caddy over HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Every error in the contract format (contracts/schemas/error.schema.json).
    "EXCEPTION_HANDLER": "apps.common.errors.exception_handler",
}

REST_FRAMEWORK.update(
    {
        "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
        "DEFAULT_THROTTLE_RATES": {"anon": env("THROTTLE_ANON", "60/min")},
    }
)

# Business rules confirmed in docs/architecture/ARCHITECTURE-RECOMMENDATION.md section 11
# and the requirements document (Chapter 4). Change them here, not in code.
GATEWAY_RULES = {
    "CURRENCY": "SGD",
    "MIN_AMOUNT_CENTS": 50,  # S$0.50
    "MAX_AMOUNT_CENTS": 1_000_000,  # S$10,000
    "IDEMPOTENCY_TTL_HOURS": 24,
    # A key left "in progress" by a crashed request is taken over after this long.
    "IDEMPOTENCY_STALE_SECONDS": 60,
    "API_RATE_LIMIT_PER_MINUTE": 100,  # per API key (NFR-AVA-02, contract section 2)
    "AUTH_EXPIRY_DAYS": 7,  # uncaptured authorisations are cancelled by the worker
    "VERIFICATION_CODE_TTL_MINUTES": 10,
    "VERIFICATION_MAX_ATTEMPTS": 3,  # requirements FR CP-6, confirmed 5 Nov 2026
    "CHECKOUT_SESSION_TTL_MINUTES": 60,
    # Guest status check (contracts/API-CONTRACT.md section 8; values confirmed 13 Nov 2026)
    "GUEST_STATUS_CODE_TTL_MINUTES": 10,
    "GUEST_STATUS_MAX_ATTEMPTS": 3,  # wrong codes before the check is locked
    "GUEST_STATUS_LOCK_MINUTES": 15,
    "GUEST_STATUS_SESSION_MINUTES": 15,  # how long an unlocked payment stays viewable
    "GUEST_STATUS_CODE_REQUESTS_PER_PAIR": 3,  # per reference + email, per 15 minutes
    "GUEST_STATUS_CODE_REQUESTS_PER_IP": 10,  # per IP address, per 15 minutes
    "PASSWORD_RESET_LINK_TTL_MINUTES": 30,  # single use (contract section 9, confirmed 13 Nov 2026)
    "SCREENING_TARGET_P95_MS": 200,
    "SCREENING_TIMEOUT_MS": 500,  # on timeout: Blocked, reason screening_unavailable
    "STAFF_LOCKOUT_FAILURES": 5,
    "STAFF_LOCKOUT_MINUTES": 15,
    "WEBHOOK_SIGNATURE_TOLERANCE_SECONDS": 300,
    # Webhook delivery (contract section 7, confirmed 13 Nov 2026): retry for 72 h from the first
    # failure with these delays (+/-10% jitter), then a final attempt at 72 h; then undelivered.
    "WEBHOOK_TIMEOUT_SECONDS": 10,
    "WEBHOOK_RETRY_WINDOW_HOURS": 72,
    "WEBHOOK_RETRY_DELAYS_SECONDS": (
        60, 300, 900, 1800, 3600, 7200, 14400, 28800, 43200, 43200, 43200, 43200,
    ),
    "RECONCILIATION_MAX_CHECKS": 6,
}

SIMULATOR_URL = env("SIMULATOR_URL", "http://localhost:8001")
# Public address of the hosted checkout; the payment's checkout_url is this + "/cs_...".
CHECKOUT_BASE_URL = env("CHECKOUT_BASE_URL", "https://localhost:8443/pay")
# Fernet key for secrets the gateway must read back (merchant signing secrets).
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = secret(
    "field_encryption_key",
    base64.urlsafe_b64encode(b"dev-only-field-encryption-key!!!").decode() if DEBUG else None,
)
CARD_FINGERPRINT_KEY = secret("card_fingerprint_key", "dev-only-fingerprint-key" if DEBUG else None)
