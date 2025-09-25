from __future__ import annotations
from typing import Any, Dict, Iterable, Mapping

def _as_list(x):
    return x if isinstance(x, list) else []

def _simplify(content: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(content, Mapping):
        return {}

    out: Dict[str, Any] = {}
    abs_in = _as_list(content.get("abstract"))
    if abs_in:
        abs_out = []
        for sec in abs_in:
            title = (sec or {}).get("title")
            body = (sec or {}).get("body") or ""
            if body.strip():
                abs_out.append({"title": title, "paragraphs": [body.strip()]})
        if abs_out:
            out["abstract"] = abs_out

    body_in = _as_list(content.get("body"))
    if body_in:
        body_out = []
        for sec in body_in:
            if not isinstance(sec, Mapping):
                continue
            title = sec.get("title")
            paras = []
            for p in _as_list(sec.get("paragraphs")):
                md = (p or {}).get("markdown") if isinstance(p, Mapping) else str(p)
                if isinstance(md, str) and md.strip():
                    paras.append(md.strip())
            if not paras:
                md = sec.get("markdown")
                if isinstance(md, str) and md.strip():
                    paras = [x.strip() for x in md.split("\n\n") if x.strip()]
            simplified = {}
            if title: simplified["title"] = title
            if paras: simplified["paragraphs"] = paras
            if simplified:
                body_out.append(simplified)
        if body_out:
            out["body"] = body_out

    kw = content.get("keywords")
    if isinstance(kw, Iterable) and not isinstance(kw, (str, bytes)):
        keywords = [str(k).strip() for k in kw if str(k).strip()]
        if keywords:
            out["keywords"] = keywords

    return out

def build_reduced_view(*, content: Mapping[str, Any] | None, meta: Mapping[str, Any] | None,
                       references: Iterable[Mapping[str, Any]] | None, title: str | None) -> Dict[str, Any]:
    view: Dict[str, Any] = {}
    metadata = dict(meta or {})
    if title and not metadata.get("title"):
        metadata["title"] = title
    view["metadata"] = metadata
    simplified = _simplify(content)
    view.update(simplified)
    view["references"] = [dict(r) for r in (references or []) if isinstance(r, Mapping)]
    return view
