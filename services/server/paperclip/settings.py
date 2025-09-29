# services/server/paperclip/settings.py
from __future__ import annotations
from pathlib import Path
import os

# --- Base paths ---
PROJECT_DIR = Path(__file__).resolve().parent           # .../services/server/paperclip
SERVICE_DIR  = PROJECT_DIR.parent                       # .../services/server
MONOREPO_ROOT = SERVICE_DIR.parent.parent               # .../
DATA_DIR = MONOREPO_ROOT / "data"
(DATA_DIR / "artifacts").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "analysis").mkdir(parents=True, exist_ok=True)

# --- Core ---
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret")
DEBUG = (os.environ.get("DEBUG", "1").lower() in {"1", "true", "yes"})
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "*").split(",") if h]  # dev-friendly

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    # Use AppConfig so ready() runs (FTS hooks, sqlite pragmas)
    "captures.app.CapturesConfig",
    "analysis",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "paperclip.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [PROJECT_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

WSGI_APPLICATION = "paperclip.wsgi.application"

# --- DB (sqlite by default; short timeout plays nicer with concurrent dev writes) ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SERVICE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

# --- Static files (avoid warning if folder absent) ---
STATIC_URL = "/static/"
STATICFILES_DIRS = [p for p in [PROJECT_DIR / "static"] if p.exists()]
STATIC_ROOT = SERVICE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Time / locale ---
TIME_ZONE = "America/Vancouver"
USE_TZ = True

# --- Paperclip dirs ---
ARTIFACTS_DIR = DATA_DIR / "artifacts"
ANALYSIS_DIR = DATA_DIR / "analysis"

# --- CORS / DRF (dev-friendly defaults; lock down in prod) ---
CORS_ALLOW_ALL_ORIGINS = True  # restrict to your extension ID in prod
REST_FRAMEWORK = {
    # Make POSTs from the extension simple during dev
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# --- Plugins / security ---
PAPERCLIP_PLUGINS = {
    "artifact_store": "paperclip.plugins.builtins.store_fs:FileSystemStore",
    "enrichers": ["paperclip.plugins.builtins.crossref:CrossrefEnricher"],
    "exporters": ["paperclip.plugins.builtins.export_csv:CSVExporter"],
}

# Allow same-origin iframe for /graph/embed/
X_FRAME_OPTIONS = "SAMEORIGIN"

# --- Logging (compact console) ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
