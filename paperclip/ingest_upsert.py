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
) -> tuple[str, bool, list[str]]:
    """
    DB upsert + IntegrityError fallback.

    Preserves existing behavior:
      - upsert captures and capture_text
      - on IntegrityError: find existing row (DOI first, then url_hash)
      - if existing_id != capture_id: copy artifacts if dst missing; cleanup new dir
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

        return existing_id, False, cleanup_dirs

    except Exception:
        try:
            shutil.rmtree(cap_dir)
        except Exception:
            pass
        raise
