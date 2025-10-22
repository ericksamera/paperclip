# services/server/paperclip/settings_typecheck.py
from __future__ import annotations

"""
Shim for django-stubs / mypy.
The plugin imports this module to read INSTALLED_APPS, DATABASES, etc.
We simply re-export the real settings so no side-effects change.
"""
from .settings import *  # noqa: F401,F403
