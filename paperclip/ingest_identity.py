from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repo import ingest_repo


@dataclass(frozen=True)
class IdentityDecision:
    capture_id: str
    created: bool
    created_at: str
    cleanup_dirs: list[str]


def dedupe_identity(
    *,
    db,
    dto: dict[str, Any],
    url_hash_value: str,
    artifacts_root: Path,
    fts_enabled: bool,
    now: str,
) -> IdentityDecision:
    """
    Identity/dedupe policy (kept stable):

    - Prefer DOI match when DOI exists
    - If DOI match exists, also check url_hash and merge duplicates into the DOI capture
      (move collection membership, delete drop capture, delete FTS row if enabled)
    - Else fall back to url_hash
    - Else create new UUID
    """
    doi = str(dto.get("doi") or "")
    cleanup_dirs: list[str] = []

    # Prefer DOI match
    if doi:
        row = ingest_repo.find_capture_by_doi(db, doi=doi)
        if row:
            capture_id = row["id"]
            created_at = row["created_at"]

            # If there's also a url_hash match to a different capture, merge it into the DOI capture.
            row_by_url = ingest_repo.find_capture_by_url_hash(
                db, url_hash=url_hash_value
            )
            if row_by_url and row_by_url["id"] != capture_id:
                drop_id = row_by_url["id"]
                ingest_repo.merge_duplicate_capture(
                    db,
                    keep_id=capture_id,
                    drop_id=drop_id,
                    fts_enabled=fts_enabled,
                )
                drop_dir = artifacts_root / drop_id
                if drop_dir.exists():
                    cleanup_dirs.append(os.fspath(drop_dir))

            return IdentityDecision(
                capture_id=capture_id,
                created=False,
                created_at=created_at,
                cleanup_dirs=cleanup_dirs,
            )

    # Fall back to url_hash
    row = ingest_repo.find_capture_by_url_hash(db, url_hash=url_hash_value)
    if row:
        return IdentityDecision(
            capture_id=row["id"],
            created=False,
            created_at=row["created_at"],
            cleanup_dirs=cleanup_dirs,
        )

    # New capture
    return IdentityDecision(
        capture_id=str(uuid.uuid4()),
        created=True,
        created_at=now,
        cleanup_dirs=cleanup_dirs,
    )
