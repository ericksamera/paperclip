from __future__ import annotations

import json
import os
import shutil
import sqlite3
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .capture_dto import build_capture_dto_from_payload
from .parsers import parse_article
from .parsers.base import ParseResult
from .timeutil import utc_now_iso
from .urlnorm import canonicalize_url, url_hash


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


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _merge_duplicates(
    *,
    db,
    keep_id: str,
    drop_id: str,
    artifacts_root: Path,
    fts_enabled: bool,
) -> Path | None:
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
        try:
            db.execute("DELETE FROM capture_fts WHERE capture_id = ?", (drop_id,))
        except Exception:
            pass

    db.execute("DELETE FROM captures WHERE id = ?", (drop_id,))
    drop_dir = artifacts_root / drop_id
    return drop_dir if drop_dir.exists() else None


@dataclass(frozen=True)
class IngestResult:
    capture_id: str
    created: bool
    summary: dict[str, Any]
    cleanup_dirs: list[str]


def ingest_capture(
    *,
    payload: dict[str, Any],
    db,
    artifacts_root: Path,
    fts_enabled: bool,
) -> IngestResult:
    now = utc_now_iso()

    source_url = str(payload.get("source_url") or "").strip()
    if not source_url:
        raise ValueError("Missing required field: source_url")

    canon = canonicalize_url(source_url)
    h = url_hash(canon)

    # --- Parser (best-effort; ingestion must survive failures) ---
    dom_html = str(payload.get("dom_html") or "")
    extraction = _as_dict(payload.get("extraction"))
    client_meta = _as_dict(extraction.get("meta"))

    parse_exc: dict[str, Any] | None = None
    try:
        # parse_article expects head_meta; we only have client_meta here, but the DTO builder
        # will also parse head meta from dom_html. This is fine for stage 1.
        parse_result = parse_article(
            url=canon, dom_html=dom_html, head_meta=client_meta
        )
    except Exception as e:
        parse_exc = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc(),
        }
        parse_result = ParseResult(
            ok=False,
            parser="crashed",
            capture_quality="suspicious",
            notes=["parser_exception"],
        )

    # --- DTO (single canonical shaping point) ---
    dto = build_capture_dto_from_payload(
        payload=payload,
        canon_url=canon,
        captured_at=now,
        parse_result=parse_result,
        parse_exc=parse_exc,
    )

    title = str(dto["title"] or "")
    doi = str(dto["doi"] or "")
    year = dto["year"]
    container_title = str(dto["container_title"] or "")
    authors = dto["authors"] if isinstance(dto.get("authors"), list) else []
    abstract = str(dto["abstract"] or "")
    keywords = dto["keywords"] if isinstance(dto.get("keywords"), list) else []
    date_str = str(dto.get("published_date_raw") or "")
    meta_record = dto["meta_record"]
    content_text = str(dto.get("content_text") or "")
    parse_summary = dto["parse_summary"]

    # --- Dedupe / identity (existing behavior preserved) ---
    capture_id: str
    created: bool
    created_at: str
    cleanup_dirs: list[str] = []

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
                "SELECT id FROM captures WHERE url_hash = ?",
                (h,),
            ).fetchone()
            if row_by_url and row_by_url["id"] != capture_id:
                to_delete_dir = _merge_duplicates(
                    db=db,
                    keep_id=capture_id,
                    drop_id=row_by_url["id"],
                    artifacts_root=artifacts_root,
                    fts_enabled=fts_enabled,
                )
                if to_delete_dir is not None:
                    cleanup_dirs.append(os.fspath(to_delete_dir))

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

    # --- Artifact writing (unchanged outputs) ---
    cap_dir = artifacts_root / capture_id
    _ensure_dir(cap_dir)

    _write_text(cap_dir / "page.html", dto.get("dom_html") or "")
    _write_text(cap_dir / "content.html", dto.get("content_html") or "")

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
        "meta": dto.get("merged_head_meta") or {},
        "parse": parse_summary,
        "stats": {
            "dom_chars": len(dto.get("dom_html") or ""),
            "content_html_chars": len(dto.get("content_html") or ""),
            "content_text_chars": len(content_text or ""),
            "article_html_chars": len(article_html or ""),
            "article_text_chars": len(article_text or ""),
        },
        "client": dto.get("client") if isinstance(dto.get("client"), dict) else {},
    }
    _write_json(cap_dir / "reduced.json", reduced)

    # --- DB upsert (unchanged schema) ---
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
                json.dumps(meta_record, ensure_ascii=False),
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

            for name in (
                "page.html",
                "content.html",
                "article.html",
                "article.txt",
                "article.json",
                "raw.json",
                "reduced.json",
            ):
                src = cap_dir / name
                dst = existing_dir / name
                if src.exists() and not dst.exists():
                    shutil.copyfile(src, dst)

            cleanup_dirs.append(os.fspath(cap_dir))

        capture_id = existing_id
        created = False

    except Exception:
        try:
            shutil.rmtree(cap_dir)
        except Exception:
            pass
        raise

    summary = {
        "id": capture_id,
        "created": created,
        "title": title,
        "doi": doi,
        "year": year,
        "container_title": container_title,
        "artifact_dir": os.fspath(artifacts_root / capture_id),
    }
    return IngestResult(
        capture_id=capture_id,
        created=created,
        summary=summary,
        cleanup_dirs=cleanup_dirs,
    )
