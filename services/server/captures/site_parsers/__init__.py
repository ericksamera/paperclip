# services/server/captures/site_parsers/__init__.py
# Registry + public API. Site modules (pmc/sciencedirect/...) self-register on import.
from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from re import Pattern
from urllib.parse import urlparse

# --------------------------- Reference registry ---------------------------
Parser = Callable[[str, str], list[dict[str, object]]]


@dataclass
class Rule:
    pattern: Pattern[str]  # compiled regex
    where: str  # "host" or "url"
    parser: Parser
    name: str


_REGISTRY: list[Rule] = []


def _compile_pattern(p: str | Pattern[str], where: str) -> Pattern[str]:
    if isinstance(p, re.Pattern):
        return p
    s = p.strip()
    if where == "host":
        if not any(ch in s for ch in "^$.*?[](){}\\"):
            s = r"(?:^|\.)" + re.escape(s) + r"$"
        return re.compile(s, re.I)
    return re.compile(s, re.I)


def register(
    pattern: str | Pattern[str], parser: Parser, *, where: str = "host", name: str = ""
) -> None:
    where = where.lower()
    if where not in ("host", "url"):
        raise ValueError('where must be "host" or "url"')
    _REGISTRY.append(
        Rule(
            pattern=_compile_pattern(pattern, where),
            where=where,
            parser=parser,
            name=name or str(pattern),
        )
    )


def clear_registry() -> None:
    _REGISTRY.clear()


def get_registry() -> list[tuple[str, str]]:
    return [(r.name, r.where) for r in _REGISTRY]


# --------------------------- Meta/Sections registry ---------------------------
MetaParser = Callable[[str, str], dict[str, object]]


@dataclass
class MetaRule:
    pattern: Pattern[str]
    where: str  # "host" or "url"
    parser: MetaParser
    name: str


_REG_META: list[MetaRule] = []


def register_meta(
    pattern: str | Pattern[str], parser: MetaParser, *, where: str = "host", name: str = ""
) -> None:
    where = where.lower()
    if where not in ("host", "url"):
        raise ValueError('where must be "host" or "url"')
    _REG_META.append(
        MetaRule(
            pattern=_compile_pattern(pattern, where),
            where=where,
            parser=parser,
            name=name or str(pattern),
        )
    )


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
    
    with suppress(Exception):
        from .bmc import parse_bmc
        register(r"(?:^|\.)biomedcentral\.com$", parse_bmc, where="host", name="BMC references")
        register(r"biomedcentral[-\.]", parse_bmc, where="url", name="BMC references (proxy)")

    with suppress(Exception):
        from .pmc import parse_pmc

        register(r"(?:^|\.)pmc\.ncbi\.nlm\.nih\.gov$", parse_pmc, where="host", name="PMC host")
        register(r"ncbi\.nlm\.nih\.gov/.*/pmc/|/pmc/", parse_pmc, where="url", name="PMC path")
    with suppress(Exception):
        from .sciencedirect import parse_sciencedirect

        register(
            r"(?:^|\.)sciencedirect\.com$", parse_sciencedirect, where="host", name="ScienceDirect"
        )
        register(
            r"sciencedirect[-\.]", parse_sciencedirect, where="url", name="ScienceDirect (proxy)"
        )
    with suppress(Exception):
        from .wiley import parse_wiley

        register(
            r"(?:^|\.)onlinelibrary\.wiley\.com$",
            parse_wiley,
            where="host",
            name="Wiley Online Library",
        )
        register(r"onlinelibrary[-\.]wiley", parse_wiley, where="url", name="Wiley (proxy)")
    # NEW: Frontiers references
    with suppress(Exception):
        from .frontiers import parse_frontiers

        register(
            r"(?:^|\.)frontiersin\.org$", parse_frontiers, where="host", name="Frontiers references"
        )
        register(
            r"frontiersin[-\.]", parse_frontiers, where="url", name="Frontiers references (proxy)"
        )
    # NEW: PLOS references
    with suppress(Exception):
        from .plos import parse_plos

        register(r"(?:^|\.)plos\.org$", parse_plos, where="host", name="PLOS references")
        register(
            r"(?:journals[-\.]plos|plosone|plosbiology|ploscompbiol|plosgenetics|plospathogens)",
            parse_plos,
            where="url",
            name="PLOS references (path)",
        )
    # NEW: OUP references
    with suppress(Exception):
        from .oup import parse_oup

        register(r"(?:^|\.)academic\.oup\.com$", parse_oup, where="host", name="OUP references")
        register(r"oup\.com/", parse_oup, where="url", name="OUP references (path)")
    # NEW: Nature references
    with suppress(Exception):
        from .nature import parse_nature

        register(r"(?:^|\.)nature\.com$", parse_nature, where="host", name="Nature references")
        register(r"nature\.com/", parse_nature, where="url", name="Nature references (path)")
    with suppress(Exception):
        from .mdpi import parse_mdpi

        register(r"(?:^|\.)mdpi\.com$", parse_mdpi, where="host", name="MDPI references")
        register(r"mdpi\.com/", parse_mdpi, where="url", name="MDPI references (path)")

def _ensure_default_meta_rules() -> None:
    """
    Mirror of _ensure_default_rules for meta/sections.
    Only registers handlers that the site modules actually expose.
    """
    if _REG_META:
        return
    
    with suppress(Exception):
        from .bmc import extract_bmc_meta
        register_meta(r"(?:^|\.)biomedcentral\.com$", extract_bmc_meta, where="host", name="BMC meta")
        register_meta(r"biomedcentral[-\.]", extract_bmc_meta, where="url", name="BMC meta (proxy)")

    with suppress(Exception):
        from .sciencedirect import extract_sciencedirect_meta

        register_meta(
            r"(?:^|\.)sciencedirect\.com$",
            extract_sciencedirect_meta,
            where="host",
            name="ScienceDirect meta",
        )
        register_meta(
            r"sciencedirect[-\.]",
            extract_sciencedirect_meta,
            where="url",
            name="ScienceDirect meta (proxy)",
        )
    with suppress(Exception):
        from .wiley import extract_wiley_meta

        register_meta(
            r"(?:^|\.)onlinelibrary\.wiley\.com$",
            extract_wiley_meta,
            where="host",
            name="Wiley meta",
        )
        register_meta(
            r"onlinelibrary[-\.]wiley", extract_wiley_meta, where="url", name="Wiley meta (proxy)"
        )
    with suppress(Exception):
        from .pmc import extract_pmc_meta

        register_meta(
            r"(?:^|\.)pmc\.ncbi\.nlm\.nih\.gov$", extract_pmc_meta, where="host", name="PMC meta"
        )
        register_meta(
            r"ncbi\.nlm\.nih\.gov/.*/pmc/|/pmc/",
            extract_pmc_meta,
            where="url",
            name="PMC meta (path)",
        )
    with suppress(Exception):
        from .frontiers import extract_frontiers_meta

        register_meta(
            r"(?:^|\.)frontiersin\.org$",
            extract_frontiers_meta,
            where="host",
            name="Frontiers meta",
        )
        register_meta(
            r"frontiersin[-\.]", extract_frontiers_meta, where="url", name="Frontiers meta (proxy)"
        )
    with suppress(Exception):
        from .plos import extract_plos_meta

        register_meta(r"(?:^|\.)plos\.org$", extract_plos_meta, where="host", name="PLOS meta")
        register_meta(
            r"(?:journals[-\.]plos|plosone|plosbiology|ploscompbiol|plosgenetics|plospathogens)",
            extract_plos_meta,
            where="url",
            name="PLOS meta (path)",
        )
    with suppress(Exception):
        from .oup import extract_oup_meta

        register_meta(
            r"(?:^|\.)academic\.oup\.com$", extract_oup_meta, where="host", name="OUP meta"
        )
        register_meta(r"oup\.com/", extract_oup_meta, where="url", name="OUP meta (path)")
    with suppress(Exception):
        from .nature import extract_nature_meta

        register_meta(
            r"(?:^|\.)nature\.com$", extract_nature_meta, where="host", name="Nature meta"
        )
        register_meta(r"nature\.com/", extract_nature_meta, where="url", name="Nature meta (path)")
    with suppress(Exception):
        from .mdpi import extract_mdpi_meta

        register_meta(r"(?:^|\.)mdpi\.com$", extract_mdpi_meta, where="host", name="MDPI meta")
        register_meta(r"mdpi\.com/", extract_mdpi_meta, where="url", name="MDPI meta (path)")

def extract_references(url: str | None, dom_html: str) -> list[dict[str, object]]:
    """
    Route by registry:
      • host rules (e.g., r"(?:^|\\.)sciencedirect\\.com$")
      • url rules  (e.g., r"ncbi\\.nlm\\.nih\\.gov/.*/pmc/")
    First matching parser that returns non-empty wins; otherwise generic fallback.
    """
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


def extract_sections_meta(url: str | None, dom_html: str) -> dict[str, object]:
    """
    Route to site meta/sections extractors when available.
    Returns a dict (possibly empty) with keys:
    abstract:str?, keywords:list[str], sections:list[dict].
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
            out.setdefault("abstract", None)
            out.setdefault("keywords", [])
            out.setdefault("sections", [])
            return out
    return {}


# --------------------------- Utilities ---------------------------
def dedupe_references(refs: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    Stable in-order de-duplication for reference dicts.
    Preference:
      1) If DOI present → normalize (case/scheme-insensitive) and dedupe by DOI
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


# Import built-ins so they call register() at import time
from . import (  # noqa: E402,F401
    frontiers,
    mdpi,
    nature,
    oup,
    plos,
    pmc,
    sciencedirect,
    wiley,
    bmc,
)
