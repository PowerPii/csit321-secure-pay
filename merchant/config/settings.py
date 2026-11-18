"""
Django settings for the demo merchant.

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
# The Django admin has no two-step sign-in, so it is routed only in development unless
# DJANGO_ADMIN=1 says otherwise. Off on the public server (Fifa, 14 Nov 2026; deploy/RUNBOOK.md).
ADMIN_ENABLED = env("DJANGO_ADMIN", "1" if DEBUG else "0") == "1"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.shop",
    "apps.webhooks",
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
        "NAME": env("POSTGRES_DB", "merchant"),
        "USER": env("POSTGRES_USER", "merchant"),
        "PASSWORD": secret("db_password", "merchant"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "ATOMIC_REQUESTS": False,
        # Keep each worker's connection open between requests instead of opening (and
        # authenticating) a new one per request; checked before reuse (Codex release review,
        # checkout profile, 18 Nov 2026).
        "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
    }
}

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
TIME_ZONE = "Asia/Singapore"  # a Singapore store: dates on pages in SGT; the DB keeps UTC
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

# --- SecurePay ----------------------------------------------------------------------------
# The shop is an ordinary merchant: it holds an API key and a signing secret, both shown once
# by the gateway's `manage.py create_merchant "Demo Shop"`, and calls the gateway's /v1 API.
SECUREPAY_API_URL = env("SECUREPAY_API_URL", "http://localhost:8000")
SECUREPAY_API_KEY = secret("securepay_api_key")
SECUREPAY_SIGNING_SECRET = secret("securepay_signing_secret")
# CA bundle for the gateway's certificate (Caddy's local CA in the Compose stack).
SECUREPAY_CA_BUNDLE = env("SECUREPAY_CA_BUNDLE", "")
SECUREPAY_TIMEOUT_SECONDS = float(env("SECUREPAY_TIMEOUT_SECONDS", "15"))
# Signed replies more than this far from our clock are rejected (API-CONTRACT.md section 2).
SECUREPAY_SIGNATURE_TOLERANCE_SECONDS = 300
# Public HTTPS address of this shop; the payment's return_url is built from it.
SHOP_BASE_URL = env("SHOP_BASE_URL", "https://shop.localhost")
SHOP_NAME = "Volt & Co."  # fictional store played by the demo merchant
CSRF_TRUSTED_ORIGINS = [SHOP_BASE_URL]  # forms post through Caddy over HTTPS
