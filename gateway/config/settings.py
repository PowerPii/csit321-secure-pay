"""
Django settings for the gateway.

Configuration comes from environment variables, and secrets from files
mounted by Docker Compose under /run/secrets (see deploy/secrets/).
Nothing secret is committed to the repository.
"""
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
    "AUTH_EXPIRY_DAYS": 7,  # uncaptured authorisations are cancelled by the worker
    "VERIFICATION_CODE_TTL_MINUTES": 10,
    "VERIFICATION_MAX_ATTEMPTS": 3,  # requirements FR CP-6; see docs/MVP-SCOPE.md open point 1
    "CHECKOUT_SESSION_TTL_MINUTES": 60,
    "GUEST_STATUS_LINK_TTL_DAYS": 30,
    "SCREENING_TARGET_P95_MS": 200,
    "SCREENING_TIMEOUT_MS": 500,  # on timeout: Blocked, reason screening_unavailable
    "STAFF_LOCKOUT_FAILURES": 5,
    "STAFF_LOCKOUT_MINUTES": 15,
    "WEBHOOK_SIGNATURE_TOLERANCE_SECONDS": 300,
    "WEBHOOK_MAX_ATTEMPTS": 8,
    "RECONCILIATION_MAX_CHECKS": 6,
}

SIMULATOR_URL = env("SIMULATOR_URL", "http://localhost:8001")
CARD_FINGERPRINT_KEY = secret("card_fingerprint_key", "dev-only-fingerprint-key" if DEBUG else None)
