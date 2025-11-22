from django import template
from django.conf import settings
from django.templatetags.static import static as _static

register = template.Library()


@register.simple_tag
def staticv(path: str) -> str:
    """
    Like {% static %} but appends ?v=<STATIC_BUILD_ID> for cache busting.
    Set STATIC_BUILD_ID in settings or env.
    """
    base = _static(path)
    ver = getattr(settings, "STATIC_BUILD_ID", "dev")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}v={ver}"
