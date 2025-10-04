# Minimal, import-safe Django settings for mypy/django-stubs.
from __future__ import annotations

from pathlib import Path

# --- Paths (match real layout so relative imports work) ---
PROJECT_DIR = Path(__file__).resolve().parent  # services/server/paperclip
SERVICE_DIR = PROJECT_DIR.parent  # services/server
MONOREPO_ROOT = SERVICE_DIR.parent.parent  # repo root

# --- Core ---
SECRET_KEY = "typecheck-only"
DEBUG = False
ALLOWED_HOSTS: list[str] = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Your local apps (plain module names avoid AppConfig.ready() side effects)
    "captures",
    "analysis",
]

MIDDLEWARE: list[str] = []  # not needed for type checking

ROOT_URLCONF = "paperclip.settings_typecheck"
urlpatterns: list = []  # satisfies Django import when ROOT_URLCONF points here

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

DATA_DIR = MONOREPO_ROOT / "data"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
ANALYSIS_DIR = DATA_DIR / "analysis"

TIME_ZONE = "America/Vancouver"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
