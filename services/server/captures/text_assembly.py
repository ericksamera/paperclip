from __future__ import annotations

from typing import Any, Mapping, Sequence

from captures.reduced_view import read_reduced_view
from captures.types import CSL  # typed but tolerant
from captures.keywords import split_keywords


def _flatten_sections_text(nodes: object) -> list[str]:
    out: list[str] = []
    if not isinstance(nodes, list):
        return out

    def walk(n: object) -> None:
        if not isinstance(n, dict):
            return
        for p in n.get("paragraphs") or []:
            if p:
                out.append(str(p))
        for ch in n.get("children") or []:
            walk(ch)

    for n in nodes:
        walk(n)
    return out


def body_text_from_view(capture_id: str) -> str:
    """
    Prefer the reduced-view preview paragraphs we persist on disk.
    """
    try:
        view = read_reduced_view(capture_id) or {}
        sec = (view.get("sections") or {}).get("abstract_or_body")
        if isinstance(sec, list):
            parts = [str(x).strip() for x in sec if x]
            return " ".join(p for p in parts if p)
        if isinstance(sec, str):
            return sec.strip() or ""
        return ""
    except Exception:
        return ""


def body_text_from_meta(meta: Mapping[str, Any], csl: CSL | Mapping[str, Any]) -> str:
    """
    Assemble lightweight body from meta & CSL blobs:
      • meta.abstract or csl.abstract
      • meta.sections paragraphs
    """
    bits: list[str] = []
    if meta.get("abstract"):
        bits.append(str(meta.get("abstract")))
    else:
        csl_map: Mapping[str, Any] = csl if isinstance(csl, Mapping) else {}
        if csl_map.get("abstract"):
            bits.append(str(csl_map.get("abstract")))
    bits.extend(_flatten_sections_text(meta.get("sections") or []))
    return " ".join(bits)


def assemble_body_text(
    *,
    capture_id: str,
    meta: Mapping[str, Any] | None,
    csl: CSL | Mapping[str, Any] | None,
    keywords: Sequence[str] | str | None = None,
) -> str:
    """
    One-stop body builder used by FTS and analysis:
      reduced-view preview + meta/csl + keywords (if provided).
    """
    meta = meta or {}
    csl = csl or {}
    parts: list[str] = []

    meta_view = body_text_from_meta(meta, csl)
    if meta_view:
        parts.append(meta_view)

    rv_view = body_text_from_view(capture_id)
    if rv_view:
        parts.append(rv_view)

    # Keywords (string → split; list → stringify)
    if isinstance(keywords, str):
        kws = split_keywords(keywords)
    elif isinstance(keywords, (list, tuple)):
        kws = [str(k) for k in keywords if k]
    else:
        kws = []
    if kws:
        parts.extend(kws)

    return " ".join([p for p in parts if p])
