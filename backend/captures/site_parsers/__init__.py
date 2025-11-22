# services/server/captures/site_parsers/__init__.py
# Public API + lazy default registrations.
from __future__ import annotations

from contextlib import suppress

# Re-export the pure router (no side effects on import)
from .router import (  # noqa: F401
    MetaParser,
    MetaRule,
    Parser,
    Rule,
    clear_meta_registry,
    clear_registry,
    dedupe_references,
    get_registry,
    register,
    register_meta,
    route_references,
    route_sections_meta,
)

# --------------------------- Lazy default registration ---------------------------


def _ensure_default_rules() -> None:
    """
    Some call-sites/tests may clear the registry. If the registry is empty at the
    moment of routing, we lazily import built-in site parsers to (re)register them.
    """
    # If anything is already registered, don't load defaults.
    if get_registry():
        return

    # Import modules that call register()/register_meta() at import-time.
    # Each block is shielded so one bad import doesn't break the rest.
    with suppress(Exception):
        from . import bmc as _bmc  # noqa: F401
    with suppress(Exception):
        from . import pmc as _pmc  # noqa: F401
    with suppress(Exception):
        from . import sciencedirect as _sciencedirect  # noqa: F401
    with suppress(Exception):
        from . import wiley as _wiley  # noqa: F401
    with suppress(Exception):
        from . import frontiers as _frontiers  # noqa: F401
    with suppress(Exception):
        from . import plos as _plos  # noqa: F401
    with suppress(Exception):
        from . import oup as _oup  # noqa: F401
    with suppress(Exception):
        from . import nature as _nature  # noqa: F401
    with suppress(Exception):
        from . import mdpi as _mdpi  # noqa: F401


def _ensure_default_meta_rules() -> None:
    # Mirror the behavior: defaults are loaded together by _ensure_default_rules.
    _ensure_default_rules()


# --------------------------- Public, friendly API ---------------------------


def extract_references(url: str | None, dom_html: str) -> list[dict[str, object]]:
    """
    Route by registry; if empty, lazily register built-ins and retry.
    First *non-empty* site parser wins; else fall back to generic.
    """
    _ensure_default_rules()
    return route_references(url, dom_html)


def extract_sections_meta(url: str | None, dom_html: str) -> dict[str, object]:
    """
    Route site meta/sections extractors when available.
    Always returns a dict with (abstract?, keywords, sections) keys.
    """
    _ensure_default_meta_rules()
    return route_sections_meta(url, dom_html)


__all__ = [
    # types
    "Parser",
    "MetaParser",
    "Rule",
    "MetaRule",
    # registry controls
    "register",
    "register_meta",
    "clear_registry",
    "clear_meta_registry",
    "get_registry",
    # high-level API (lazy defaults)
    "extract_references",
    "extract_sections_meta",
    # util
    "dedupe_references",
]
