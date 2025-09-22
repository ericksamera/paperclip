from __future__ import annotations
from typing import Any, Dict, List
from .utils import normalize_title

def text_for_embedding(doc: Dict[str, Any]) -> str:
    csl = doc.get("csl") or {}
    parts: List[str] = []
    for key in ("title", "abstract", "abstractText"):
        v = csl.get(key) if isinstance(csl, dict) else None
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    # Fallbacks from parsed payload
    if not parts and isinstance(doc.get("title"), str):
        parts.append(doc["title"])
    if isinstance(doc.get("headings"), list):
        parts.extend([h for h in doc["headings"] if isinstance(h, str)])
    # As a last resort, compress visible text sample if present
    if isinstance(doc.get("text_sample"), str):
        parts.append(doc["text_sample"][:2000])
    return "\n".join(parts).strip()

def references_from_doc(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    refs = doc.get("references") or []
    out: List[Dict[str, Any]] = []
    for r in refs:
        if not isinstance(r, dict):
            continue
        out.append({
            "doi": r.get("doi") or r.get("DOI") or "",
            "title": (r.get("title") or r.get("unstructured") or "").strip(),
        })
    return out

def title_of(doc: Dict[str, Any]) -> str:
    csl = doc.get("csl") or {}
    title = csl.get("title") if isinstance(csl, dict) else None
    return (title or doc.get("title") or "").strip()

def norm_title_of(doc: Dict[str, Any]) -> str:
    return normalize_title(title_of(doc))

def extract_text(content: Dict[str, Any]) -> str:
    parts: List[str] = []
    for a in (content.get("abstract") or []):
        parts.append(a.get("body") or "")
    for sec in (content.get("body") or []):
        if sec.get("markdown"):
            parts.append(sec["markdown"])
        for p in (sec.get("paragraphs") or []):
            if p.get("markdown"):
                parts.append(p["markdown"])
    # Fallbacks
    if not parts and content.get("fulltext"):
        parts.append(content["fulltext"])
    return "\n\n".join(p for p in parts if p).strip()
