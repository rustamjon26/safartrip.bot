"""
Django settings for backend project.

Production-ready basics:
- Secrets and config are loaded from environment (.env in local dev)
- Database uses DATABASE_URL (PostgreSQL recommended). Falls back to SQLite for local dev only.
- DEBUG and ALLOWED_HOSTS are env-driven.
"""

from pathlib import Path
import os

from dotenv import load_dotenv
import dj_database_url

# -----------------------------------------------------------------------------
# Paths & Env
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env from repo root (../.. relative to this file) for local development.
# In production, prefer setting environment variables in the server platform.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


def _require_env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(
            f"❌ Required environment variable '{name}' is missing.\n"
            f"   Set it in .env (local) or server environment (production)."
        )
    return v


# -----------------------------------------------------------------------------
# Core settings
# -----------------------------------------------------------------------------
SECRET_KEY = _require_env("DJANGO_SECRET_KEY")

DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() in ("true", "1", "yes")

_allowed_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "").strip()
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(",") if h.strip()] if _allowed_hosts else []

# In DEBUG mode, allow localhost by default if not set
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Optional security hardening for production (recommended)
# If you're behind a proxy (nginx, railway, render), set DJANGO_SECURE_PROXY_SSL_HEADER=true
if os.getenv("DJANGO_SECURE_PROXY_SSL_HEADER", "false").lower() in ("true", "1", "yes"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# -----------------------------------------------------------------------------
# Applications
# -----------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Add your apps here, for example:
    # "booking",
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

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "backend.wsgi.application"


# -----------------------------------------------------------------------------
# Database (PostgreSQL via DATABASE_URL; fallback to SQLite for local dev only)
# -----------------------------------------------------------------------------
# Put this into .env:
# DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
#
# If your provider requires SSL, set:
# PGSSLMODE=require

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    # ssl_require will enforce SSL if PGSSLMODE=require
    ssl_required = os.getenv("PGSSLMODE", "").lower() == "require"

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=ssl_required,
        )
    }
else:
    # Local fallback (not recommended for production)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# -----------------------------------------------------------------------------
# Password validation
# -----------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# -----------------------------------------------------------------------------
# Internationalization
# -----------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


# -----------------------------------------------------------------------------
# Static files
# -----------------------------------------------------------------------------
STATIC_URL = "static/"

# If you serve static with whitenoise/nginx, you can set STATIC_ROOT:
STATIC_ROOT = os.getenv("DJANGO_STATIC_ROOT", "").strip() or None
if STATIC_ROOT:
    STATIC_ROOT = str(Path(STATIC_ROOT))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
