# services/server/captures/reduced_view.py
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

# Public schema
from .types import ReducedSections, ReducedView, SectionNode

# -----------------------------------------------------------------------------
# Canonical / legacy basenames
# -----------------------------------------------------------------------------
CANONICAL_REDUCED_BASENAME: str = "server_output_reduced.json"
LEGACY_REDUCED_BASENAMES: tuple[str, ...] = ("view.json", "parsed.json")

__all__ = [
    "CANONICAL_REDUCED_BASENAME",
    "LEGACY_REDUCED_BASENAMES",
    "build_reduced_view",
    "read_reduced_view",
]

# -----------------------------------------------------------------------------
# Internal: small coercers that make arbitrary dicts safe to work with
# -----------------------------------------------------------------------------


def _as_list_str(x: object) -> List[str]:
    if isinstance(x, list):
        return [str(p) for p in x if p is not None]
    if isinstance(x, str):
        return [x]
    return []


def _coerce_section_node(obj: object) -> SectionNode:
    if not isinstance(obj, Mapping):
        return SectionNode()  # empty
    title = str(obj.get("title") or "") if obj.get("title") is not None else ""
    paragraphs = _as_list_str(obj.get("paragraphs"))
    children_raw = obj.get("children")
    children: List[SectionNode] = []
    if isinstance(children_raw, Iterable) and not isinstance(
        children_raw, (str, bytes)
    ):
        for ch in children_raw:
            children.append(_coerce_section_node(ch))
    node: SectionNode = SectionNode()
    if title:
        node["title"] = title
    if paragraphs:
        node["paragraphs"] = paragraphs
    if children:
        node["children"] = children
    return node


def _coerce_sections(obj: object) -> ReducedSections:
    out: ReducedSections = ReducedSections(
        abstract=None, abstract_or_body=[], sections=[]
    )
    if not isinstance(obj, Mapping):
        return out
    # abstract
    abs_val = obj.get("abstract")
    if isinstance(abs_val, str) and abs_val.strip():
        out["abstract"] = abs_val.strip()
    # abstract_or_body
    aob = obj.get("abstract_or_body")
    out["abstract_or_body"] = _as_list_str(aob)
    # sections
    sections_raw = obj.get("sections")
    nodes: List[SectionNode] = []
    if isinstance(sections_raw, Iterable) and not isinstance(
        sections_raw, (str, bytes)
    ):
        for n in sections_raw:
            node = _coerce_section_node(n)
            if node.get("title") or node.get("paragraphs") or node.get("children"):
                nodes.append(node)
    if nodes:
        out["sections"] = nodes
    return out


def _empty_reduced(title: str = "") -> ReducedView:
    return ReducedView(
        title=title or "",
        meta={},
        sections=ReducedSections(abstract=None, abstract_or_body=[], sections=[]),
        references=[],
    )


def _coerce_reduced(obj: object) -> ReducedView:
    """
    Accept anything vaguely dict-ish and produce a well-formed ReducedView.
    Unknown keys are ignored; missing keys are added.
    """
    if not isinstance(obj, Mapping):
        return _empty_reduced()
    title = str(obj.get("title") or "")
    meta = dict(obj.get("meta") or {})
    sections = _coerce_sections(obj.get("sections") or {})
    refs_raw = obj.get("references") or []
    references: List[Dict[str, Any]] = []
    if isinstance(refs_raw, Iterable) and not isinstance(refs_raw, (str, bytes)):
        for r in refs_raw:
            try:
                references.append(dict(r))  # be generous
            except Exception:
                pass
    return ReducedView(title=title, meta=meta, sections=sections, references=references)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def build_reduced_view(
    *,
    content: Mapping[str, Any] | None,
    meta: Mapping[str, Any] | None,
    references: Iterable[Mapping[str, Any]] | None,
    title: str | None,
) -> ReducedView:
    """
    Tiny, stable summary we persist as reduced view.

    This function is intentionally tolerant to slightly different inputs and
    guarantees all top-level keys will exist in the output.
    """
    sections = _coerce_sections(content or {})
    meta_dict: Dict[str, Any] = dict(meta or {})
    refs_list: List[Dict[str, Any]] = [dict(r) for r in (references or [])]
    return ReducedView(
        title=(title or "").strip(),
        meta=meta_dict,
        sections=sections,
        references=refs_list,
    )


def read_reduced_view(capture_id: str) -> ReducedView:
    """
    Read the reduced projection from disk, tolerant to historical filenames.

    We accept any of:
      • view.json                     (legacy UI projection)
      • server_output_reduced.json    (current canonical reduced projection)
      • parsed.json                   (legacy alias for reduced)

    Always returns a *well-formed* ReducedView with all keys present.
    """
    try:
        from paperclip.artifacts import read_json_artifact
    except Exception:
        # Extremely defensive: if the artifacts module isn't available,
        # act as if the capture has no reduced view yet.
        return _empty_reduced()

    # Preserve legacy-first read order to avoid visible behavior changes
    read_order = (
        LEGACY_REDUCED_BASENAMES[0],
        CANONICAL_REDUCED_BASENAME,
        LEGACY_REDUCED_BASENAMES[1],
    )
    for name in read_order:
        try:
            data = read_json_artifact(str(capture_id), name, default=None)
        except Exception:
            data = None
        if data:
            return _coerce_reduced(data)

    return _empty_reduced()
