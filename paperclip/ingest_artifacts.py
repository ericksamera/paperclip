from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .parsers.base import ParseResult


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _atomic_write_bytes(p: Path, b: bytes) -> None:
    _ensure_dir(p.parent)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(b)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, p)


def _write_text(p: Path, text: str) -> None:
    data = (text or "").encode("utf-8", errors="ignore")
    _atomic_write_bytes(p, data)


def _write_json(p: Path, obj: Any) -> None:
    s = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _atomic_write_bytes(p, s.encode("utf-8", errors="ignore"))


@dataclass(frozen=True)
class ArtifactWriteResult:
    cap_dir: Path
    article_html: str
    article_text: str


def write_capture_artifacts(
    *,
    artifacts_root: Path,
    capture_id: str,
    dto: dict[str, Any],
    parse_result: ParseResult,
    parse_exc: dict[str, Any] | None,
    raw_payload: dict[str, Any],
    source_url: str,
    canon_url: str,
    captured_at: str,
) -> ArtifactWriteResult:
    """
    Writes the same artifact set as before:
      - page.html, content.html
      - article.html/article.txt if non-empty
      - article.json (always)
      - raw.json (always, original request payload)
      - reduced.json (always)
    """
    cap_dir = artifacts_root / capture_id
    _ensure_dir(cap_dir)

    _write_text(cap_dir / "page.html", str(dto.get("dom_html") or ""))
    _write_text(cap_dir / "content.html", str(dto.get("content_html") or ""))

    article_html = parse_result.article_html or ""
    article_text = parse_result.article_text or ""

    if article_html:
        _write_text(cap_dir / "article.html", article_html)
    if article_text:
        _write_text(cap_dir / "article.txt", article_text)

    article_json = parse_result.to_json()
    if parse_exc:
        article_json["error"] = parse_exc
    _write_json(cap_dir / "article.json", article_json)

    _write_json(
        cap_dir / "raw.json", {"received_at": captured_at, "payload": raw_payload}
    )

    content_text = str(dto.get("content_text") or "")
    title = str(dto.get("title") or "")
    doi = str(dto.get("doi") or "")
    year = dto.get("year", None)
    container_title = str(dto.get("container_title") or "")
    authors = dto.get("authors") if isinstance(dto.get("authors"), list) else []
    abstract = str(dto.get("abstract") or "")
    keywords = dto.get("keywords") if isinstance(dto.get("keywords"), list) else []
    date_str = str(dto.get("published_date_raw") or "")
    parse_summary = dto.get("parse_summary") or {}

    reduced = {
        "id": capture_id,
        "source_url": source_url,
        "canonical_url": canon_url,
        "title": title,
        "doi": doi,
        "year": year,
        "container_title": container_title,
        "authors": authors,
        "abstract": abstract,
        "published_date_raw": date_str,
        "keywords": keywords,
        "captured_at": captured_at,
        "meta": dto.get("merged_head_meta") or {},
        "parse": parse_summary,
        "stats": {
            "dom_chars": len(str(dto.get("dom_html") or "")),
            "content_html_chars": len(str(dto.get("content_html") or "")),
            "content_text_chars": len(content_text or ""),
            "article_html_chars": len(article_html or ""),
            "article_text_chars": len(article_text or ""),
        },
        "client": dto.get("client") if isinstance(dto.get("client"), dict) else {},
    }
    _write_json(cap_dir / "reduced.json", reduced)

    return ArtifactWriteResult(
        cap_dir=cap_dir, article_html=article_html, article_text=article_text
    )
