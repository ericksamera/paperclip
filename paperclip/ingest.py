from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .extract import (
    best_abstract,
    best_authors,
    best_container_title,
    best_date,
    best_doi,
    best_keywords,
    best_title,
    extract_year,
    html_to_text,
    parse_head_meta,
)
from .timeutil import utc_now_iso
from .urlnorm import canonicalize_url, url_hash


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


def _merge_duplicates(
    *,
    db,
    keep_id: str,
    drop_id: str,
    artifacts_root: Path,
    fts_enabled: bool,
) -> Path | None:
    """
    Merge drop_id into keep_id (best effort):
      - move collection membership
      - delete the dropped capture row (cascades capture_text + collection_items)
      - return the artifacts dir to delete after commit
    """
    if not keep_id or not drop_id or keep_id == drop_id:
        return None

    rows = db.execute(
        "SELECT collection_id, added_at FROM collection_items WHERE capture_id = ?",
        (drop_id,),
    ).fetchall()
    for r in rows:
        db.execute(
            "INSERT OR IGNORE INTO collection_items (collection_id, capture_id, added_at) VALUES (?, ?, ?)",
            (r["collection_id"], keep_id, r["added_at"]),
        )

    if fts_enabled:
        db.execute("DELETE FROM capture_fts WHERE capture_id = ?", (drop_id,))

    db.execute("DELETE FROM captures WHERE id = ?", (drop_id,))

    drop_dir = artifacts_root / drop_id
    return drop_dir if drop_dir.exists() else None


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
      - de-dupe by DOI when available (normalized)
      - otherwise de-dupe by canonical URL hash
      - write artifacts to disk
      - upsert DB row + search text
    """
    now = utc_now_iso()

    source_url = str(payload.get("source_url") or "").strip()
    dom_html = str(payload.get("dom_html") or "")
    extraction = _as_dict(payload.get("extraction"))
    content_html = str(extraction.get("content_html") or "")
    client_meta = _as_dict(extraction.get("meta"))

    if not source_url:
        raise ValueError("Missing required field: source_url")
    if not dom_html:
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
    authors = best_authors(meta)
    abstract = best_abstract(meta)
    content_text = html_to_text(content_html)

    capture_id: str
    created: bool
    created_at: str

    row = None
    if doi:
        row = db.execute(
            "SELECT id, created_at FROM captures WHERE doi = ? AND doi <> '' LIMIT 1",
            (doi,),
        ).fetchone()

        if row:
            capture_id = row["id"]
            created = False
            created_at = row["created_at"]

            row_by_url = db.execute(
                "SELECT id FROM captures WHERE url_hash = ?", (h,)
            ).fetchone()
            if row_by_url and row_by_url["id"] != capture_id:
                to_delete_dir = _merge_duplicates(
                    db=db,
                    keep_id=capture_id,
                    drop_id=row_by_url["id"],
                    artifacts_root=artifacts_root,
                    fts_enabled=fts_enabled,
                )
            else:
                to_delete_dir = None
        else:
            to_delete_dir = None
    else:
        to_delete_dir = None

    if not row:
        row = db.execute(
            "SELECT id, created_at FROM captures WHERE url_hash = ?",
            (h,),
        ).fetchone()
        if row:
            capture_id = row["id"]
            created = False
            created_at = row["created_at"]
        else:
            capture_id = str(uuid.uuid4())
            created = True
            created_at = now

    cap_dir = artifacts_root / capture_id
    _ensure_dir(cap_dir)

    _write_text(cap_dir / "page.html", dom_html)
    _write_text(cap_dir / "content.html", content_html)

    raw = {"received_at": now, "payload": payload}
    _write_json(cap_dir / "raw.json", raw)

    reduced = {
        "id": capture_id,
        "source_url": source_url,
        "canonical_url": canon,
        "title": title,
        "doi": doi,
        "year": year,
        "container_title": container_title,
        "authors": authors,
        "abstract": abstract,
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
        "authors": authors,
        "abstract": abstract,
        "published_date_raw": date_str,
        "client": reduced.get("client", {}),
    }

    try:
        db.execute(
            """
            INSERT INTO captures (
              id, url, url_canon, url_hash,
              title, doi, year, container_title,
              meta_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              url=excluded.url,
              url_canon=excluded.url_canon,
              url_hash=excluded.url_hash,
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
    except sqlite3.IntegrityError:
        row2 = None
        if doi:
            row2 = db.execute(
                "SELECT id, created_at FROM captures WHERE doi = ? AND doi <> '' LIMIT 1",
                (doi,),
            ).fetchone()
        if not row2:
            row2 = db.execute(
                "SELECT id, created_at FROM captures WHERE url_hash = ? LIMIT 1",
                (h,),
            ).fetchone()
        if not row2:
            raise

        existing_id = row2["id"]
        if existing_id != capture_id:
            existing_dir = artifacts_root / existing_id
            _ensure_dir(existing_dir)

            for name in ("page.html", "content.html", "raw.json", "reduced.json"):
                src = cap_dir / name
                if src.exists():
                    shutil.copyfile(src, existing_dir / name)

            try:
                shutil.rmtree(cap_dir)
            except Exception:
                pass

            capture_id = existing_id
            created = False
            created_at = row2["created_at"]
            cap_dir = existing_dir

        db.execute(
            """
            UPDATE captures SET
              url=?,
              url_canon=?,
              url_hash=?,
              title=?,
              doi=?,
              year=?,
              container_title=?,
              meta_json=?,
              updated_at=?
            WHERE id=?
            """,
            (
                source_url,
                canon,
                h,
                title,
                doi,
                year,
                container_title,
                json.dumps(meta_json, ensure_ascii=False),
                now,
                capture_id,
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
        db.execute("DELETE FROM capture_fts WHERE capture_id = ?", (capture_id,))
        db.execute(
            "INSERT INTO capture_fts (capture_id, title, content_text) VALUES (?, ?, ?)",
            (capture_id, title, content_text),
        )

    db.commit()

    if to_delete_dir is not None:
        try:
            shutil.rmtree(to_delete_dir)
        except Exception:
            pass

    summary = {
        "id": capture_id,
        "created": created,
        "title": title,
        "doi": doi,
        "year": year,
        "container_title": container_title,
        "artifact_dir": os.fspath(artifacts_root / capture_id),
    }
    return IngestResult(capture_id=capture_id, created=created, summary=summary)
