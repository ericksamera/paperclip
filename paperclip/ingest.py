from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .extract import (
    best_container_title,
    best_date,
    best_doi,
    best_keywords,
    best_title,
    extract_year,
    html_to_text,
    parse_head_meta,
)
from .urlnorm import canonicalize_url, url_hash


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_text(p: Path, text: str) -> None:
    p.write_text(text or "", encoding="utf-8", errors="ignore")


def _write_json(p: Path, obj: Any) -> None:
    p.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="ignore",
    )


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _merge_meta(
    client_meta: dict[str, Any], head_meta: dict[str, Any]
) -> dict[str, Any]:
    """
    Merge meta with head_meta winning on key collisions.
    Keys are normalized to lowercase strings.
    """
    out: dict[str, Any] = {}
    for src in (client_meta, head_meta):
        if not isinstance(src, dict):
            continue
        for k, v in src.items():
            kk = str(k).strip().lower()
            if not kk:
                continue
            out[kk] = v
    return out


@dataclass(frozen=True)
class IngestResult:
    capture_id: str
    created: bool
    summary: dict[str, Any]


def ingest_capture(
    *,
    payload: dict[str, Any],
    db,
    artifacts_root: Path,
    fts_enabled: bool,
) -> IngestResult:
    """
    Ingest a capture payload:
      - dedupe by canonical URL hash
      - write artifacts to disk
      - upsert DB row + search text
    """
    now = _utc_now_iso()

    source_url = str(payload.get("source_url") or "").strip()
    dom_html = str(payload.get("dom_html") or "")
    extraction = _as_dict(payload.get("extraction"))
    content_html = str(extraction.get("content_html") or "")
    client_meta = _as_dict(extraction.get("meta"))

    if not source_url:
        raise ValueError("Missing required field: source_url")
    if not dom_html:
        # Allow empty DOM in theory, but it's usually a caller bug.
        # Keep behavior permissive (some pages block scripts).
        dom_html = ""

    canon = canonicalize_url(source_url)
    h = url_hash(canon)

    head_meta, title_tag_text = parse_head_meta(dom_html)
    meta = _merge_meta(client_meta, head_meta)

    title = best_title(meta, title_tag_text, source_url)
    doi = best_doi(meta)
    date_str = best_date(meta)
    year = extract_year(date_str)
    container_title = best_container_title(meta)
    keywords = best_keywords(meta)
    content_text = html_to_text(content_html)

    # Dedupe: canonical URL hash
    row = db.execute(
        "SELECT id, created_at FROM captures WHERE url_hash = ?", (h,)
    ).fetchone()
    if row:
        capture_id = row["id"]
        created = False
        created_at = row["created_at"]
    else:
        capture_id = str(uuid.uuid4())
        created = True
        created_at = now

    # Artifacts on disk
    cap_dir = artifacts_root / capture_id
    _ensure_dir(cap_dir)

    _write_text(cap_dir / "page.html", dom_html)
    _write_text(cap_dir / "content.html", content_html)

    raw = {
        "received_at": now,
        "payload": payload,
    }
    _write_json(cap_dir / "raw.json", raw)

    reduced = {
        "id": capture_id,
        "source_url": source_url,
        "canonical_url": canon,
        "title": title,
        "doi": doi,
        "year": year,
        "container_title": container_title,
        "published_date_raw": date_str,
        "keywords": keywords,
        "captured_at": now,
        "meta": meta,
        "stats": {
            "dom_chars": len(dom_html or ""),
            "content_html_chars": len(content_html or ""),
            "content_text_chars": len(content_text or ""),
        },
        "client": (
            payload.get("client") if isinstance(payload.get("client"), dict) else {}
        ),
    }
    _write_json(cap_dir / "reduced.json", reduced)

    meta_json = {
        "meta": meta,
        "keywords": keywords,
        "published_date_raw": date_str,
        "client": reduced.get("client", {}),
    }

    # DB upsert
    db.execute(
        """
        INSERT INTO captures (
          id, url, url_canon, url_hash,
          title, doi, year, container_title,
          meta_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url_hash) DO UPDATE SET
          url=excluded.url,
          url_canon=excluded.url_canon,
          title=excluded.title,
          doi=excluded.doi,
          year=excluded.year,
          container_title=excluded.container_title,
          meta_json=excluded.meta_json,
          updated_at=excluded.updated_at
        """,
        (
            capture_id,
            source_url,
            canon,
            h,
            title,
            doi,
            year,
            container_title,
            json.dumps(meta_json, ensure_ascii=False),
            created_at,
            now,
        ),
    )

    db.execute(
        """
        INSERT INTO capture_text (capture_id, content_text)
        VALUES (?, ?)
        ON CONFLICT(capture_id) DO UPDATE SET
          content_text=excluded.content_text
        """,
        (capture_id, content_text),
    )

    if fts_enabled:
        # Keep it simple: delete + insert
        db.execute("DELETE FROM capture_fts WHERE capture_id = ?", (capture_id,))
        db.execute(
            "INSERT INTO capture_fts (capture_id, title, content_text) VALUES (?, ?, ?)",
            (capture_id, title, content_text),
        )

    db.commit()

    summary = {
        "id": capture_id,
        "created": created,
        "title": title,
        "doi": doi,
        "year": year,
        "container_title": container_title,
        "artifact_dir": os.fspath(cap_dir),
    }
    return IngestResult(capture_id=capture_id, created=created, summary=summary)
