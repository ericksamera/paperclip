# services/server/captures/site_parsers/__init__.py
# Registry + public API. Site modules (pmc/sciencedirect/…) self-register on import.
from __future__ import annotations
from typing import Callable, Dict, List, Tuple, Pattern, Union
from dataclasses import dataclass
import re
from urllib.parse import urlparse

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

# Default generic parser (imported after helpers)
from .generic import parse_generic as _DEFAULT_PARSER  # noqa: E402

def extract_references(url: str | None, dom_html: str) -> List[Dict[str, object]]:
    """
    Route by registry:
      • host rules (e.g., r"(?:^|\\.)sciencedirect\\.com$")
      • url rules  (e.g., r"ncbi\\.nlm\\.nih\\.gov/.*/pmc/")
    First matching parser that returns non-empty wins; otherwise generic fallback.
    """
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

# De-dupe shared util
def dedupe_references(refs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    from .base import norm_doi  # lazy import to avoid cycles
    out: List[Dict[str, str]] = []
    seen_doi = set()
    seen_raw = set()
    for r in refs or []:
        doi_key = norm_doi(r.get("doi"))
        raw_key = (r.get("raw") or "").strip().lower()
        if doi_key:
            if doi_key in seen_doi: continue
            seen_doi.add(doi_key)
        else:
            if raw_key in seen_raw: continue
            seen_raw.add(raw_key)
        out.append(r)
    return out

# Import built-ins so they call register() at import time
from . import sciencedirect  # noqa: F401,E402
from . import pmc            # noqa: F401,E402
