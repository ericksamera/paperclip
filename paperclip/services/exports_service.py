from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from ..export import captures_to_bibtex, captures_to_ris
from ..paper_md import render_paper_markdown
from ..parseutil import safe_int
from ..queryparams import get_collection_arg
from ..repo import exports_repo


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:80] if s else "export"


@dataclass(frozen=True)
class ExportContext:
    captures: list[dict]
    capture_id: str | None
    col_id: int | None
    col_name: str | None


def select_export_context(
    db,
    *,
    capture_id: str | None,
    col: str | None,
) -> ExportContext:
    """
    Service-level decision logic:
      - if capture_id provided => export that one capture (if it exists; otherwise empty)
      - else if collection id provided => export that collection (and attach col_name)
      - else => export all
    """
    cap_id = (capture_id or "").strip() or None
    col_raw = (col or "").strip() or None

    if cap_id:
        cap = exports_repo.get_capture_by_id(db, capture_id=cap_id)
        caps = [cap] if cap else []
        return ExportContext(
            captures=caps, capture_id=cap_id, col_id=None, col_name=None
        )

    col_id = safe_int(col_raw)
    if col_id and col_id > 0:
        caps = exports_repo.list_captures_in_collection(db, collection_id=int(col_id))
        col_name = exports_repo.get_collection_name(db, collection_id=int(col_id))
        return ExportContext(
            captures=caps, capture_id=None, col_id=int(col_id), col_name=col_name
        )

    caps = exports_repo.list_all_captures(db)
    return ExportContext(captures=caps, capture_id=None, col_id=None, col_name=None)


def export_filename(
    *,
    ext: str,
    capture_id: str | None,
    col_id: int | None,
    col_name: str | None,
    selected: bool,
    suffix: str | None = None,
) -> str:
    base = "paperclip"

    if capture_id:
        base = f"{base}_{_slug(capture_id)[:12]}"
    elif col_name:
        base = f"{base}_{_slug(col_name)}"
    elif col_id:
        base = f"{base}_col{col_id}"

    if suffix:
        base = f"{base}_{_slug(suffix)}"

    if selected:
        base = f"{base}_selected"

    return f"{base}.{ext}"


ExportKind = Literal["bibtex", "ris"]


def render_export(*, kind: ExportKind, captures: list[dict]) -> tuple[str, str]:
    """
    Returns (body, mimetype).
    """
    if kind == "bibtex":
        return captures_to_bibtex(captures), "application/x-bibtex"
    if kind == "ris":
        return captures_to_ris(captures), "application/x-research-info-systems"
    raise ValueError(f"Unknown export kind: {kind}")


def select_captures_by_ids(db, *, capture_ids: list[str]) -> list[dict]:
    return exports_repo.select_captures_by_ids(db, capture_ids=capture_ids)


def export_download_parts_from_args(
    db,
    *,
    kind: ExportKind,
    args: Mapping[str, Any],
) -> tuple[str, str, str]:
    """
    Thin-route helper: parse args, select captures, render, and return (body, mimetype, filename).
    """
    col = get_collection_arg(args) or None
    capture_id = (str(args.get("capture_id") or "")).strip() or None

    ctx = select_export_context(db, capture_id=capture_id, col=col)
    body, mimetype = render_export(kind=kind, captures=ctx.captures)

    ext = "bib" if kind == "bibtex" else "ris"
    filename = export_filename(
        ext=ext,
        capture_id=ctx.capture_id,
        col_id=ctx.col_id,
        col_name=ctx.col_name,
        selected=False,
    )
    return body, mimetype, filename


def export_selected_download_parts(
    db,
    *,
    kind: ExportKind,
    capture_ids: list[str],
) -> tuple[str, str, str]:
    """
    Thin-route helper for selected exports: returns (body, mimetype, filename).
    """
    captures = select_captures_by_ids(db, capture_ids=capture_ids)
    body, mimetype = render_export(kind=kind, captures=captures)

    ext = "bib" if kind == "bibtex" else "ris"
    filename = export_filename(
        ext=ext,
        capture_id=None,
        col_id=None,
        col_name=None,
        selected=True,
    )
    return body, mimetype, filename


# -------------------------
# Master Markdown export
# -------------------------


def _read_text_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _cap_dir(artifacts_root: Path, capture_id: str) -> Path:
    return artifacts_root / str(capture_id)


def _paper_md_for_capture(*, artifacts_root: Path, cap: dict[str, Any]) -> str:
    """
    Prefer the prebuilt paper.md artifact. Fallback to a minimal markdown synthesis using:
      - reduced.json (if present) for metadata
      - article.txt / references.txt for content
    """
    cap_id = str(cap.get("id") or "").strip()
    if not cap_id:
        return ""

    cap_dir = _cap_dir(artifacts_root, cap_id)
    p_paper = cap_dir / "paper.md"
    if p_paper.exists():
        return _read_text_file(p_paper).rstrip() + "\n"

    # Fallback: build from disk artifacts, not DB (keeps export stable even if DB changes)
    title = str(cap.get("title") or "").strip()
    doi = str(cap.get("doi") or "").strip()
    container_title = str(cap.get("container_title") or "").strip()
    year = cap.get("year", None)
    year_i = int(year) if isinstance(year, int) else None
    source_url = str(cap.get("url") or "").strip()

    article_text = _read_text_file(cap_dir / "article.txt").strip()
    refs_text = _read_text_file(cap_dir / "references.txt").strip()

    # If no parsed text exists, still export a shell so user can see it in the bundle.
    sections = []
    if article_text:
        sections = [
            {"id": "s01", "title": "Body", "kind": "other", "text": article_text}
        ]

    return render_paper_markdown(
        title=title,
        source_url=source_url,
        doi=doi,
        container_title=container_title,
        year=year_i,
        sections=sections,
        references_text=refs_text,
    )


def render_master_markdown(
    *,
    captures: list[dict[str, Any]],
    artifacts_root: Path,
    title: str,
) -> str:
    """
    Concatenate paper.md blobs with a simple top header + separators.
    """
    out: list[str] = []
    out.append(f"# {title}".strip())
    out.append("")
    out.append(f"_Items: {len(captures)}_")
    out.append("")

    first = True
    for cap in captures:
        blob = _paper_md_for_capture(artifacts_root=artifacts_root, cap=cap).strip()
        if not blob:
            continue
        if not first:
            out.append("\n---\n")
        out.append(blob.rstrip() + "\n")
        first = False

    return "\n".join(out).rstrip() + "\n"


def master_md_download_parts_from_args(
    db,
    *,
    args: Mapping[str, Any],
    artifacts_root: Path,
) -> tuple[str, str, str]:
    """
    GET /exports/master.md/?collection=<id>&capture_id=<id>
    """
    col = get_collection_arg(args) or None
    capture_id = (str(args.get("capture_id") or "")).strip() or None

    ctx = select_export_context(db, capture_id=capture_id, col=col)

    title = "Paperclip Master Export"
    if ctx.col_name:
        title = f"Paperclip Master Export — {ctx.col_name}"
    elif ctx.col_id:
        title = f"Paperclip Master Export — Collection {ctx.col_id}"
    elif ctx.capture_id:
        title = f"Paperclip Master Export — {ctx.capture_id}"

    body = render_master_markdown(
        captures=ctx.captures,
        artifacts_root=artifacts_root,
        title=title,
    )
    mimetype = "text/markdown; charset=utf-8"
    filename = export_filename(
        ext="md",
        capture_id=ctx.capture_id,
        col_id=ctx.col_id,
        col_name=ctx.col_name,
        selected=False,
        suffix="master",
    )
    return body, mimetype, filename


def master_md_selected_download_parts(
    db,
    *,
    capture_ids: list[str],
    artifacts_root: Path,
) -> tuple[str, str, str]:
    captures = select_captures_by_ids(db, capture_ids=capture_ids)

    body = render_master_markdown(
        captures=captures,
        artifacts_root=artifacts_root,
        title="Paperclip Master Export — Selected",
    )
    mimetype = "text/markdown; charset=utf-8"
    filename = export_filename(
        ext="md",
        capture_id=None,
        col_id=None,
        col_name=None,
        selected=True,
        suffix="master",
    )
    return body, mimetype, filename


# -------------------------
# Sections JSON export
# -------------------------


def _read_json_file(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _sections_for_capture(*, artifacts_root: Path, cap_id: str) -> list[dict[str, Any]]:
    """
    Prefer artifacts/<id>/sections.json; otherwise empty.
    """
    if not cap_id:
        return []
    p = (artifacts_root / cap_id) / "sections.json"
    if not p.exists():
        return []
    v = _read_json_file(p)
    return v if isinstance(v, list) else []


def render_sections_export_json(
    *,
    captures: list[dict[str, Any]],
    artifacts_root: Path,
) -> str:
    """
    Returns a JSON string: list[dict] where each dict is:
      { id, title, url, doi, year, container_title, sections: [...] }
    """
    out: list[dict[str, Any]] = []
    for cap in captures:
        cap_id = str(cap.get("id") or "").strip()
        if not cap_id:
            continue
        out.append(
            {
                "id": cap_id,
                "title": str(cap.get("title") or ""),
                "url": str(cap.get("url") or ""),
                "doi": str(cap.get("doi") or ""),
                "year": cap.get("year", None),
                "container_title": str(cap.get("container_title") or ""),
                "sections": _sections_for_capture(
                    artifacts_root=artifacts_root, cap_id=cap_id
                ),
            }
        )

    return json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sections_json_download_parts_from_args(
    db,
    *,
    args: Mapping[str, Any],
    artifacts_root: Path,
) -> tuple[str, str, str]:
    """
    GET /exports/sections.json/?collection=<id>&capture_id=<id>
    """
    col = get_collection_arg(args) or None
    capture_id = (str(args.get("capture_id") or "")).strip() or None

    ctx = select_export_context(db, capture_id=capture_id, col=col)

    body = render_sections_export_json(
        captures=ctx.captures, artifacts_root=artifacts_root
    )
    mimetype = "application/json; charset=utf-8"
    filename = export_filename(
        ext="json",
        capture_id=ctx.capture_id,
        col_id=ctx.col_id,
        col_name=ctx.col_name,
        selected=False,
        suffix="sections",
    )
    return body, mimetype, filename


def sections_json_selected_download_parts(
    db,
    *,
    capture_ids: list[str],
    artifacts_root: Path,
) -> tuple[str, str, str]:
    """
    POST /exports/sections.json/selected/ with capture_ids
    """
    captures = select_captures_by_ids(db, capture_ids=capture_ids)

    body = render_sections_export_json(captures=captures, artifacts_root=artifacts_root)
    mimetype = "application/json; charset=utf-8"
    filename = export_filename(
        ext="json",
        capture_id=None,
        col_id=None,
        col_name=None,
        selected=True,
        suffix="sections",
    )
    return body, mimetype, filename


# -------------------------
# Papers JSONL export (LLM-friendly)
# -------------------------


# Section kinds we exclude from papers.jsonl (noise for “read the paper” use cases)
_PAPERS_EXCLUDE_KINDS = {
    "acknowledgements",
    "author_contributions",
    "funding",
    "conflicts",
    # usually not useful as body text (and can be huge/duplicative on some sites)
    "keywords",
}


def _filtered_sections_for_papers_export(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in sections:
        if not isinstance(s, dict):
            continue
        kind = str(s.get("kind") or "").strip()
        if kind in _PAPERS_EXCLUDE_KINDS:
            continue
        text = str(s.get("text") or "").strip()
        if not text:
            continue

        out.append(
            {
                "id": str(s.get("id") or ""),
                "kind": kind,
                "title": str(s.get("title") or ""),
                "text": text,
            }
        )
    return out


def _reduced_for_capture(*, artifacts_root: Path, cap_id: str) -> dict[str, Any]:
    """
    Best-effort: read reduced.json (for stable metadata + parse summary).
    If missing/unreadable, return {}.
    """
    if not cap_id:
        return {}
    p = (artifacts_root / cap_id) / "reduced.json"
    v = _read_json_file(p) if p.exists() else None
    return v if isinstance(v, dict) else {}


def render_papers_export_jsonl(
    *,
    captures: list[dict[str, Any]],
    artifacts_root: Path,
) -> str:
    """
    Returns NDJSON (JSONL) with one line per capture.

    Each line shape (Option A):
      {
        id, title, doi, url, year, container_title, authors,
        capture_quality, confidence_fulltext,
        sections: [{id, kind, title, text}, ...]
      }

    Notes:
      - Sections are sourced from artifacts/<id>/sections.json (preferred).
      - Metadata is sourced from artifacts/<id>/reduced.json when available,
        falling back to DB row fields.
      - Certain section kinds are excluded (acknowledgements, funding, etc.).
    """
    lines: list[str] = []
    for cap in captures:
        cap_id = str(cap.get("id") or "").strip()
        if not cap_id:
            continue

        reduced = _reduced_for_capture(artifacts_root=artifacts_root, cap_id=cap_id)

        # metadata: prefer reduced.json; fallback to DB row
        title = str(reduced.get("title") or cap.get("title") or "")
        doi = str(reduced.get("doi") or cap.get("doi") or "")
        url = str(
            reduced.get("source_url")
            or reduced.get("canonical_url")
            or cap.get("url")
            or ""
        )
        year = reduced.get("year", cap.get("year", None))
        container_title = str(
            reduced.get("container_title") or cap.get("container_title") or ""
        )
        authors = reduced.get("authors", [])
        if not isinstance(authors, list):
            authors = []

        parse_summary = reduced.get("parse", {})
        if not isinstance(parse_summary, dict):
            parse_summary = {}

        capture_quality = str(parse_summary.get("capture_quality") or "")
        confidence_fulltext = float(parse_summary.get("confidence_fulltext") or 0.0)

        sections_raw = _sections_for_capture(
            artifacts_root=artifacts_root, cap_id=cap_id
        )
        sections = _filtered_sections_for_papers_export(sections_raw)

        obj = {
            "id": cap_id,
            "title": title,
            "doi": doi,
            "url": url,
            "year": year,
            "container_title": container_title,
            "authors": authors,
            "capture_quality": capture_quality,
            "confidence_fulltext": confidence_fulltext,
            "sections": sections,
        }

        lines.append(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))

    return "\n".join(lines).rstrip() + ("\n" if lines else "")


def papers_jsonl_download_parts_from_args(
    db,
    *,
    args: Mapping[str, Any],
    artifacts_root: Path,
) -> tuple[str, str, str]:
    """
    GET /exports/papers.jsonl/?collection=<id>&capture_id=<id>
    """
    col = get_collection_arg(args) or None
    capture_id = (str(args.get("capture_id") or "")).strip() or None

    ctx = select_export_context(db, capture_id=capture_id, col=col)

    body = render_papers_export_jsonl(
        captures=ctx.captures, artifacts_root=artifacts_root
    )
    mimetype = "application/x-ndjson; charset=utf-8"
    filename = export_filename(
        ext="jsonl",
        capture_id=ctx.capture_id,
        col_id=ctx.col_id,
        col_name=ctx.col_name,
        selected=False,
        suffix="papers",
    )
    return body, mimetype, filename


def papers_jsonl_selected_download_parts(
    db,
    *,
    capture_ids: list[str],
    artifacts_root: Path,
) -> tuple[str, str, str]:
    """
    POST /exports/papers.jsonl/selected/ with capture_ids
    """
    captures = select_captures_by_ids(db, capture_ids=capture_ids)

    body = render_papers_export_jsonl(captures=captures, artifacts_root=artifacts_root)
    mimetype = "application/x-ndjson; charset=utf-8"
    filename = export_filename(
        ext="jsonl",
        capture_id=None,
        col_id=None,
        col_name=None,
        selected=True,
        suffix="papers",
    )
    return body, mimetype, filename
