from __future__ import annotations
from pathlib import Path
import json
from typing import List, Dict, Any
from .text import extract_text
from .utils import slugify

def _one_doc(fp: Path) -> Dict[str, Any]:
    obj = json.loads(fp.read_text(encoding="utf-8"))
    meta = obj.get("meta", {}) or {}
    content = obj.get("content", {}) or {}
    title = meta.get("title") or meta.get("source") or "Untitled"
    doi = meta.get("doi") or None
    url = obj.get("url") or meta.get("url") or None
    year = str(meta.get("issued_year")) if meta.get("issued_year") else None
    keywords = list(content.get("keywords") or [])
    text = extract_text(content)
    references = list(obj.get("references") or [])

    # Choose a stable id and citekey
    id_ = obj.get("id") or doi or str(fp)
    citekey = meta.get("citekey") or (slugify(title) if not doi else slugify(doi))

    return {
        "path": str(fp),
        "id": id_,
        "title": title,
        "doi": doi,
        "url": url,
        "year": year,
        "keywords": keywords,
        "text": text,
        "references": references,
        "citekey": citekey,
        "meta": meta,
        "csl": meta.get("csl") or None,
    }

def load_docs(input_patterns: List[str]) -> List[Dict[str, Any]]:
    files: List[Path] = []
    for pattern in input_patterns:
        p = Path(pattern)
        if p.is_file():
            files.append(p)
        else:
            files.extend(Path().glob(pattern))
    seen = set()
    out: List[Dict[str, Any]] = []
    for fp in sorted(set(files)):
        try:
            d = _one_doc(fp)
        except Exception as e:
            print(f"[WARN] Failed to read {fp}: {e}")
            continue
        key = d["doi"] or d["id"]
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out
