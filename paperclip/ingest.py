from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ingest_artifacts import ArtifactWriteResult, write_capture_artifacts
from .ingest_identity import IdentityDecision, dedupe_identity
from .ingest_parse import ParsedPayload, parse_payload
from .ingest_upsert import IdentityDecision as UpsertIdentityDecision
from .ingest_upsert import upsert_capture


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
    parsed: ParsedPayload = parse_payload(payload)

    identity: IdentityDecision = dedupe_identity(
        db=db,
        dto=parsed.dto,
        url_hash_value=parsed.url_hash,
        artifacts_root=artifacts_root,
        fts_enabled=fts_enabled,
        now=parsed.captured_at,
    )

    arts: ArtifactWriteResult = write_capture_artifacts(
        artifacts_root=artifacts_root,
        capture_id=identity.capture_id,
        dto=parsed.dto,
        parse_result=parsed.parse_result,
        parse_exc=parsed.parse_exc,
        raw_payload=parsed.raw_payload,
        source_url=parsed.source_url,
        canon_url=parsed.canon_url,
        captured_at=parsed.captured_at,
    )

    final_id, created, cleanup_dirs = upsert_capture(
        db=db,
        capture_id=identity.capture_id,
        identity=UpsertIdentityDecision(
            capture_id=identity.capture_id,
            created=identity.created,
            created_at=identity.created_at,
            cleanup_dirs=identity.cleanup_dirs,
        ),
        dto=parsed.dto,
        source_url=parsed.source_url,
        canon_url=parsed.canon_url,
        url_hash_value=parsed.url_hash,
        now=parsed.captured_at,
        artifacts_root=artifacts_root,
        cap_dir=arts.cap_dir,
    )

    dto = parsed.dto
    summary = {
        "id": final_id,
        "created": created,
        "title": str(dto.get("title") or ""),
        "doi": str(dto.get("doi") or ""),
        "year": dto.get("year", None),
        "container_title": str(dto.get("container_title") or ""),
        "artifact_dir": os.fspath(artifacts_root / final_id),
    }

    return IngestResult(
        capture_id=final_id,
        created=created,
        summary=summary,
        cleanup_dirs=cleanup_dirs,
    )
