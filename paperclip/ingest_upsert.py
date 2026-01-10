from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import ALLOWED_ARTIFACTS
from .repo import ingest_repo


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _capture_rowid(db, *, capture_id: str) -> int | None:
    """
    Returns the SQLite INTEGER rowid for captures.id (TEXT PK).
    Used as the stable key for capture_fts.rowid.
    """
    if not capture_id:
        return None
    try:
        row = db.execute(
            "SELECT rowid AS rid FROM captures WHERE id = ? LIMIT 1", (capture_id,)
        ).fetchone()
        if not row:
            return None
        rid = row["rid"]
        return int(rid) if rid is not None else None
    except Exception:
        return None


def _upsert_capture_fts(db, *, capture_id: str, title: str, content_text: str) -> None:
    """
    Maintain capture_fts (virtual FTS5 table) using captures.rowid as the key.

    IMPORTANT:
    - FTS5 virtual tables do NOT reliably support UPSERT's "ON CONFLICT DO UPDATE".
    - "INSERT OR REPLACE" works and keeps exactly one row per rowid.
    """
    rid = _capture_rowid(db, capture_id=capture_id)
    if rid is None:
        return

    try:
        db.execute(
            """
            INSERT OR REPLACE INTO capture_fts(rowid, title, content_text)
            VALUES(?, ?, ?)
            """,
            (rid, title or "", content_text or ""),
        )
    except sqlite3.OperationalError:
        # FTS not available on this SQLite build, or table missing
        pass
    except Exception:
        # Best-effort: never break ingest
        pass


@dataclass(frozen=True)
class IdentityDecision:
    capture_id: str
    created: bool
    created_at: str
    cleanup_dirs: list[str]


def upsert_capture(
    *,
    db,
    capture_id: str,
    identity: IdentityDecision,
    dto: dict[str, Any],
    source_url: str,
    canon_url: str,
    url_hash_value: str,
    now: str,
    artifacts_root: Path,
    cap_dir: Path,
    fts_enabled: bool,
) -> tuple[str, bool, list[str]]:
    """
    DB upsert + IntegrityError fallback.

    Preserves existing behavior:
      - upsert captures and capture_text
      - on IntegrityError: find existing row (DOI first, then url_hash)
      - if existing_id != capture_id: copy artifacts if dst missing; cleanup new dir

    NEW:
      - when fts_enabled: maintain capture_fts for the final capture id
    """
    title = str(dto.get("title") or "")
    doi = str(dto.get("doi") or "")
    year = dto.get("year", None)
    container_title = str(dto.get("container_title") or "")
    meta_record = (
        dto.get("meta_record") if isinstance(dto.get("meta_record"), dict) else {}
    )
    content_text = str(dto.get("content_text") or "")

    created_at = identity.created_at
    created = identity.created
    cleanup_dirs = list(identity.cleanup_dirs)

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
                canon_url,
                url_hash_value,
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

        if fts_enabled:
            _upsert_capture_fts(
                db, capture_id=capture_id, title=title, content_text=content_text
            )

        return capture_id, created, cleanup_dirs

    except sqlite3.IntegrityError:
        # Preserve fallback: DOI first, then url_hash
        row2 = ingest_repo.find_capture_by_doi(db, doi=doi) if doi else None
        if not row2:
            row2 = ingest_repo.find_capture_by_url_hash(db, url_hash=url_hash_value)
        if not row2:
            raise

        existing_id = row2["id"]
        if existing_id != capture_id:
            existing_dir = artifacts_root / existing_id
            _ensure_dir(existing_dir)

            for name in ALLOWED_ARTIFACTS:
                src = cap_dir / name
                dst = existing_dir / name
                if src.exists() and not dst.exists():
                    shutil.copyfile(src, dst)

            cleanup_dirs.append(os.fspath(cap_dir))

        if fts_enabled:
            _upsert_capture_fts(
                db, capture_id=existing_id, title=title, content_text=content_text
            )

        return existing_id, False, cleanup_dirs

    except Exception:
        try:
            shutil.rmtree(cap_dir)
        except Exception:
            pass
        raise
