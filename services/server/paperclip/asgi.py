import os

from django.core.asgi import get_asgi_application

# Load .env before settings
try:
    from .env import load_env as _pc_load_env

    _pc_load_env()
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paperclip.settings")
application = get_asgi_application()
