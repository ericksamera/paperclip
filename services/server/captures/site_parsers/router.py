# services/server/captures/site_parsers/router.py
from __future__ import annotations

import re
from dataclasses import dataclass
from re import Pattern
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

# Types for site parsers
Parser = Callable[[str, str], list[dict[str, object]]]
MetaParser = Callable[[str, str], dict[str, object]]

@dataclass
class Rule:
    pattern: Pattern[str]      # compiled regex
    where: str                 # "host" or "url"
    parser: Parser
    name: str

@dataclass
class MetaRule:
    pattern: Pattern[str]
    where: str                 # "host" or "url"
    parser: MetaParser
    name: str

# In-memory registries
_REGISTRY: list[Rule] = []
_REG_META: list[MetaRule] = []

def _compile_pattern(p: str | Pattern[str], where: str) -> Pattern[str]:
    if isinstance(p, re.Pattern):
        return p
    s = p.strip()
    if where == "host":
        # If it's a plain hostname, turn it into a safe anchored regex.
        if not any(ch in s for ch in "^$.*?[](){}\\"):
            s = r"(?:^|\.)" + re.escape(s) + r"$"
        return re.compile(s, re.I)
    return re.compile(s, re.I)

# ---------------- Registry API (no side effects) ----------------

def register(pattern: str | Pattern[str], parser: Parser, *, where: str = "host", name: str = "") -> None:
    where = where.lower()
    if where not in ("host", "url"):
        raise ValueError('where must be "host" or "url"')
    _REGISTRY.append(
        Rule(pattern=_compile_pattern(pattern, where), where=where, parser=parser, name=name or str(pattern))
    )

def register_meta(pattern: str | Pattern[str], parser: MetaParser, *, where: str = "host", name: str = "") -> None:
    where = where.lower()
    if where not in ("host", "url"):
        raise ValueError('where must be "host" or "url"')
    _REG_META.append(
        MetaRule(pattern=_compile_pattern(pattern, where), where=where, parser=parser, name=name or str(pattern))
    )

def clear_registry() -> None:
    _REGISTRY.clear()

def clear_meta_registry() -> None:
    _REG_META.clear()

def get_registry() -> list[tuple[str, str]]:
    """Return (name, where) for debugging/tests."""
    return [(r.name, r.where) for r in _REGISTRY]

# ---------------- Routers (no default auto-load) ----------------

def route_references(url: str | None, dom_html: str) -> list[dict[str, object]]:
    """
    Route by current registry without loading any built-in site modules.
    First *non-empty* parser wins; fallback to generic parser.
    """
    # Lazy import is safe (generic has no register() side-effects)
    from .generic import parse_generic as _DEFAULT_PARSER

    host = (urlparse(url or "").hostname or "").lower()
    full = (url or "").lower()
    for rule in _REGISTRY:
        target = host if rule.where == "host" else full
        if rule.pattern.search(target):
            try:
                refs = rule.parser(url or "", dom_html)
            except Exception:
                refs = []
            if refs:
                return refs
    return _DEFAULT_PARSER(url or "", dom_html)

def route_sections_meta(url: str | None, dom_html: str) -> dict[str, object]:
    """
    Route meta/sections extractors by current registry (no auto-load).
    Always returns a dict with keys abstract?:str, keywords:list[str], sections:list[dict].
    """
    host = (urlparse(url or "").hostname or "").lower()
    full = (url or "").lower()
    for rule in _REG_META:
        target = host if rule.where == "host" else full
        if rule.pattern.search(target):
            try:
                out = rule.parser(url or "", dom_html) or {}
            except Exception:
                out = {}
            out.setdefault("abstract", None)
            out.setdefault("keywords", [])
            out.setdefault("sections", [])
            return out
    return {}

# ---------------- Utilities ----------------

def dedupe_references(refs: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    Stable in-order de-duplication for reference dicts.
    Preference:
      1) If DOI present → normalize and dedupe by DOI
      2) Else → dedupe by lowercased 'raw' text
    """
    from paperclip.utils import norm_doi

    seen_doi: set[str] = set()
    seen_raw: set[str] = set()
    out: list[dict[str, object]] = []
    for r in refs or []:
        doi = norm_doi(str((r or {}).get("doi") or ""))
        if doi:
            if doi in seen_doi:
                continue
            seen_doi.add(doi)
        else:
            raw_key = (str((r or {}).get("raw") or "")).strip().lower()
            if raw_key in seen_raw:
                continue
            if raw_key:
                seen_raw.add(raw_key)
        out.append(r)
    return out

__all__ = [
    "Parser",
    "MetaParser",
    "Rule",
    "MetaRule",
    "register",
    "register_meta",
    "clear_registry",
    "clear_meta_registry",
    "get_registry",
    "route_references",
    "route_sections_meta",
    "dedupe_references",
]
