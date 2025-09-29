# services/server/captures/site_parsers/__init__.py
# Registry + public API. Site modules (pmc/sciencedirect/…) self-register on import.
from __future__ import annotations
from typing import Callable, Dict, List, Tuple, Pattern, Union
from dataclasses import dataclass
import re
from urllib.parse import urlparse

# --------------------------- Reference registry ---------------------------

Parser = Callable[[str, str], List[Dict[str, object]]]

@dataclass
class Rule:
    pattern: Pattern[str]        # compiled regex
    where: str                   # "host" or "url"
    parser: Parser
    name: str

_REGISTRY: List[Rule] = []

def _compile_pattern(p: Union[str, Pattern[str]], where: str) -> Pattern[str]:
    if isinstance(p, re.Pattern):
        return p
    s = p.strip()
    if where == "host":
        if not any(ch in s for ch in "^$.*?[](){}\\"):
            s = r"(?:^|\.)" + re.escape(s) + r"$"
        return re.compile(s, re.I)
    return re.compile(s, re.I)

def register(pattern: Union[str, Pattern[str]], parser: Parser, *, where: str = "host", name: str = "") -> None:
    where = where.lower()
    if where not in ("host", "url"):
        raise ValueError('where must be "host" or "url"')
    _REGISTRY.append(Rule(pattern=_compile_pattern(pattern, where), where=where, parser=parser, name=name or str(pattern)))

def clear_registry() -> None:
    _REGISTRY.clear()

def get_registry() -> List[Tuple[str, str]]:
    return [(r.name, r.where) for r in _REGISTRY]

# --------------------------- Meta/Sections registry ---------------------------

MetaParser = Callable[[str, str], Dict[str, object]]

@dataclass
class MetaRule:
    pattern: Pattern[str]
    where: str                   # "host" or "url"
    parser: MetaParser
    name: str

_REG_META: List[MetaRule] = []

def register_meta(pattern: Union[str, Pattern[str]], parser: MetaParser, *, where: str = "host", name: str = "") -> None:
    where = where.lower()
    if where not in ("host", "url"):
        raise ValueError('where must be "host" or "url"')
    _REG_META.append(MetaRule(pattern=_compile_pattern(pattern, where), where=where, parser=parser, name=name or str(pattern)))

def clear_meta_registry() -> None:
    _REG_META.clear()

# --------------------------- Routers ---------------------------

# Default generic parser (imported after helpers)
from .generic import parse_generic as _DEFAULT_PARSER  # noqa: E402

def _ensure_default_rules() -> None:
    """
    Some tests call clear_registry() and leave it empty. If that happens,
    re-register our built-in site parsers so routing still works.
    """
    if _REGISTRY:
        return
    try:
        from .pmc import parse_pmc
        register(r"(?:^|\.)pmc\.ncbi\.nlm\.nih\.gov$", parse_pmc, where="host", name="PMC host")
        register(r"ncbi\.nlm\.nih\.gov/.*/pmc/|/pmc/", parse_pmc, where="url",  name="PMC path")
    except Exception:
        pass
    try:
        from .sciencedirect import parse_sciencedirect
        register(r"(?:^|\.)sciencedirect\.com$", parse_sciencedirect, where="host", name="ScienceDirect")
        # NEW: proxy-friendly URL rule (e.g. www-sciencedirect-com.ezproxy.*)
        register(r"sciencedirect[-\.]", parse_sciencedirect, where="url", name="ScienceDirect (proxy)")
    except Exception:
        pass
    try:
        from .wiley import parse_wiley
        register(r"(?:^|\.)onlinelibrary\.wiley\.com$", parse_wiley, where="host", name="Wiley Online Library")
        register(r"onlinelibrary[-\.]wiley", parse_wiley, where="url", name="Wiley (proxy)")
    except Exception:
        pass

def _ensure_default_meta_rules() -> None:
    """
    Mirror of _ensure_default_rules for meta/sections.
    Only registers handlers that the site modules actually expose.
    """
    if _REG_META:
        return
    try:
        from .sciencedirect import extract_sciencedirect_meta
        register_meta(r"(?:^|\.)sciencedirect\.com$", extract_sciencedirect_meta, where="host", name="ScienceDirect meta")
        # NEW: proxy-friendly URL rule
        register_meta(r"sciencedirect[-\.]", extract_sciencedirect_meta, where="url", name="ScienceDirect meta (proxy)")
    except Exception:
        pass
    try:
        from .wiley import extract_wiley_meta  # type: ignore[attr-defined]
        register_meta(r"(?:^|\.)onlinelibrary\.wiley\.com$", extract_wiley_meta, where="host", name="Wiley meta")
        register_meta(r"onlinelibrary[-\.]wiley", extract_wiley_meta, where="url", name="Wiley meta (proxy)")
    except Exception:
        pass
    try:
        from .pmc import extract_pmc_meta  # type: ignore[attr-defined]
        register_meta(r"(?:^|\.)pmc\.ncbi\.nlm\.nih\.gov$", extract_pmc_meta, where="host", name="PMC meta")
        register_meta(r"ncbi\.nlm\.nih\.gov/.*/pmc/|/pmc/", extract_pmc_meta, where="url", name="PMC meta (path)")
    except Exception:
        pass

def extract_references(url: str | None, dom_html: str) -> List[Dict[str, object]]:
    """
    Route by registry:
      • host rules (e.g., r"(?:^|\\.)sciencedirect\\.com$")
      • url rules  (e.g., r"ncbi\\.nlm\\.nih\\.gov/.*/pmc/")
    First matching parser that returns non-empty wins; otherwise generic fallback.
    """
    # Auto-restore defaults if a previous test cleared the registry.
    _ensure_default_rules()

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

def extract_sections_meta(url: str | None, dom_html: str) -> Dict[str, object]:
    """
    Route to site meta/sections extractors when available.
    Returns a dict (possibly empty) with keys: abstract:str?, keywords:list[str], sections:list[dict].
    """
    _ensure_default_meta_rules()

    host = (urlparse(url or "").hostname or "").lower()
    full = (url or "").lower()
    for rule in _REG_META:
        target = host if rule.where == "host" else full
        if rule.pattern.search(target):
            try:
                out = rule.parser(url or "", dom_html) or {}
            except Exception:
                out = {}
            # Normalize shape
            out.setdefault("abstract", None)
            out.setdefault("keywords", [])
            out.setdefault("sections", [])
            return out
    return {}

# --------------------------- Utilities ---------------------------

def dedupe_references(refs: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """
    Stable in-order de-duplication for reference dicts.
    Preference:
      1) If DOI present → normalize (case/scheme-insensitive) and dedupe by DOI
      2) Else → dedupe by lowercased 'raw' text
    """
    from paperclip.utils import norm_doi
    seen_doi: set[str] = set()
    seen_raw: set[str] = set()
    out: List[Dict[str, object]] = []
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

# Import built-ins so they call register() at import time
from . import sciencedirect  # noqa: F401,E402
from . import pmc            # noqa: F401,E402
from . import wiley          # noqa: F401,E402

__all__ = [
    "register", "clear_registry", "get_registry",
    "register_meta", "clear_meta_registry",
    "extract_references", "extract_sections_meta",
    "dedupe_references",
]
