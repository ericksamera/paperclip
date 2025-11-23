from __future__ import annotations

from typing import Any, Mapping

from captures.parsing_bridge import robust_parse as _robust_parse_impl


def robust_parse(
    *, url: str | None, content_html: str, dom_html: str
) -> dict[str, Any]:
    """
    Thin wrapper around captures.parsing_bridge.robust_parse used by the ingest
    pipeline and repair tools.

    Keeping this here lets all ingest-related code import from a single
    captures.ingest namespace.
    """
    return _robust_parse_impl(url=url, content_html=content_html, dom_html=dom_html)


def _bridge_extraction(
    *,
    url: str | None,
    fb_meta: Mapping[str, Any],
    fb_secs: Mapping[str, Any],
    site: Any,
    dom_html: str,
) -> dict[str, Any]:
    """
    Rebuild a bridge payload for older captures when bridge.json is missing.

    Used by:
      - captures.reduced_view.rebuild_reduced_view
      - dev/repair tooling

    Strategy:
      - try robust_parse(dom_html) to get fresh meta_updates + content_sections
      - if sections are missing, fall back to stored fb_secs
      - if keywords are missing, fall back to fb_meta.keywords
    """
    # site is currently unused but kept for signature compatibility with existing
    # call-sites (it may be useful later if site-specific rules are added).
    _ = site  # touch to avoid “unused” warnings

    try:
        # We don't have content_html here; rely on full DOM snapshot.
        bridge = robust_parse(url=url or "", content_html="", dom_html=dom_html or "")
    except Exception:
        bridge = {}

    if not isinstance(bridge, dict):
        bridge = {}

    meta_updates = dict(bridge.get("meta_updates") or {})
    content_sections = bridge.get("content_sections") or {}

    # If robust_parse didn't give us sections, fall back to stored sections.
    if not isinstance(content_sections, Mapping) or not content_sections:
        if isinstance(fb_secs, Mapping):
            content_sections = dict(fb_secs or {})
        else:
            content_sections = {}

    # Prefer keywords from robust_parse; if missing, use fallback meta keywords.
    if "keywords" not in meta_updates and isinstance(fb_meta, Mapping):
        kws = fb_meta.get("keywords")
        if kws:
            meta_updates["keywords"] = kws

    bridge["meta_updates"] = meta_updates
    bridge["content_sections"] = content_sections
    return bridge
