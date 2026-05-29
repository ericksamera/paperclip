from __future__ import annotations

import re
from typing import Any

from .bundle import PaperBundle
from .sectionizer import classify_heading
from .text_standardize import standardize_text

# Section kinds we exclude from papers.jsonl (noise for “read the paper” use cases)
PAPERS_EXCLUDE_KINDS = {
    "acknowledgements",
    "author_contributions",
    "funding",
    "conflicts",
    "keywords",
}


def filtered_sections_for_papers_jsonl(
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in sections:
        if not isinstance(s, dict):
            continue

        kind = str(s.get("kind") or "").strip()
        if kind in PAPERS_EXCLUDE_KINDS:
            continue

        text = standardize_text(str(s.get("text") or "")).strip()
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


# Evidence-bearing section kinds emitted to chunks.jsonl.
CHUNK_EVIDENCE_KINDS = {
    "abstract",
    "results",
    "methods",
    "discussion",
    "limitations",
}
CHUNK_EXCLUDE_KINDS = {"references"}
CHUNK_KIND_PRIORITY = ("abstract", "results", "methods", "limitations", "discussion")
MAX_CHUNK_CHARS = 4500


def _safe_year(v: Any) -> int | None:
    if v is None:
        return None
    try:
        y = int(v)
    except Exception:
        return None
    return y if 1500 <= y <= 2200 else None


def _section_level(section: dict[str, Any]) -> int:
    try:
        return int(section.get("level") or 2)
    except Exception:
        return 2


def _norm_kind(kind: Any) -> str:
    return re.sub(r"\s+", "_", str(kind or "").strip().lower())


def _candidate_section_kinds(section: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    kinds = section.get("kinds")
    if isinstance(kinds, list):
        candidates.extend(_norm_kind(k) for k in kinds)

    candidates.append(_norm_kind(section.get("kind")))
    candidates.append(_norm_kind(classify_heading(str(section.get("title") or ""))))

    out: list[str] = []
    seen: set[str] = set()
    for k in candidates:
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def _direct_chunk_kind(section: dict[str, Any]) -> str:
    candidates = _candidate_section_kinds(section)

    # Preserve stable output kinds even when parsers expose multi-kind sections
    # like "results_discussion".
    for preferred in CHUNK_KIND_PRIORITY:
        if preferred in candidates:
            return preferred

    if "results_discussion" in candidates:
        return "results"
    if "references" in candidates:
        return "references"

    for k in candidates:
        if k not in {"", "other"}:
            return k
    return ""


def _sections_with_chunk_kinds(
    sections: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    """
    Classify sections for retrieval chunks.

    Parsers often expose subsections as kind="other" with either parent_id or
    a lower heading level. Inherit evidence-bearing context from the parent or
    nearest enclosing prior heading so Results/Methods subsections remain useful
    retrieval units.
    """
    out: list[tuple[dict[str, Any], str]] = []
    by_id: dict[str, str] = {}
    active_by_level: dict[int, str] = {}

    for section in sections:
        if not isinstance(section, dict):
            continue

        level = _section_level(section)
        for old_level in list(active_by_level.keys()):
            if old_level >= level:
                active_by_level.pop(old_level, None)

        direct = _direct_chunk_kind(section)
        chosen = direct

        if direct in {"", "other"}:
            parent_id = str(section.get("parent_id") or "").strip()
            parent_kind = by_id.get(parent_id, "") if parent_id else ""
            if parent_kind in CHUNK_EVIDENCE_KINDS:
                chosen = parent_kind
            else:
                for _lvl, active_kind in sorted(active_by_level.items(), reverse=True):
                    if active_kind in CHUNK_EVIDENCE_KINDS:
                        chosen = active_kind
                        break
                else:
                    chosen = ""

        sid = str(section.get("id") or "").strip()
        if sid:
            by_id[sid] = chosen

        if chosen in CHUNK_EVIDENCE_KINDS or chosen in CHUNK_EXCLUDE_KINDS:
            active_by_level[level] = chosen

        out.append((section, chosen))

    return out


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    n = len(text)
    start = max(0, min(start, n))
    end = max(start, min(end, n))
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r"[^\n]+", text or ""):
        start, end = _trim_span(text, m.start(), m.end())
        if start < end:
            spans.append((start, end))
    return spans


def _sentence_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    local = text[start:end]
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in re.finditer(r"(?<=[.!?])\s+", local):
        s0, s1 = _trim_span(text, start + pos, start + m.start())
        if s0 < s1:
            spans.append((s0, s1))
        pos = m.end()
    s0, s1 = _trim_span(text, start + pos, end)
    if s0 < s1:
        spans.append((s0, s1))
    return spans


def _hard_split_span(text: str, start: int, end: int) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    pos = start
    while pos < end:
        target = min(end, pos + MAX_CHUNK_CHARS)
        cut = target
        if target < end:
            window = text[pos:target]
            ws = max(window.rfind(" "), window.rfind("\n"), window.rfind("\t"))
            if ws > MAX_CHUNK_CHARS // 2:
                cut = pos + ws
        if cut <= pos:
            cut = target
        s0, s1 = _trim_span(text, pos, cut)
        if s0 < s1:
            chunks.append((s0, s1, text[s0:s1]))
        pos = cut
    return chunks


def _pack_sentence_spans(
    text: str, spans: list[tuple[int, int]]
) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    cur_start: int | None = None
    cur_end: int | None = None

    def flush() -> None:
        nonlocal cur_start, cur_end
        if cur_start is None or cur_end is None:
            return
        s0, s1 = _trim_span(text, cur_start, cur_end)
        if s0 < s1:
            chunks.append((s0, s1, text[s0:s1]))
        cur_start = None
        cur_end = None

    for start, end in spans:
        if end - start > MAX_CHUNK_CHARS:
            flush()
            chunks.extend(_hard_split_span(text, start, end))
            continue
        if cur_start is None:
            cur_start = start
            cur_end = end
            continue
        assert cur_end is not None
        if end - cur_start > MAX_CHUNK_CHARS:
            flush()
            cur_start = start
            cur_end = end
        else:
            cur_end = end

    flush()
    return chunks


def _pack_spans(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    cur_start: int | None = None
    cur_end: int | None = None

    def flush() -> None:
        nonlocal cur_start, cur_end
        if cur_start is None or cur_end is None:
            return
        s0, s1 = _trim_span(text, cur_start, cur_end)
        if s0 < s1:
            chunks.append((s0, s1, text[s0:s1]))
        cur_start = None
        cur_end = None

    for start, end in spans:
        if end - start > MAX_CHUNK_CHARS:
            flush()
            sentences = _sentence_spans(text, start, end)
            if len(sentences) <= 1:
                chunks.extend(_hard_split_span(text, start, end))
            else:
                chunks.extend(_pack_sentence_spans(text, sentences))
            continue

        if cur_start is None:
            cur_start = start
            cur_end = end
            continue

        assert cur_end is not None
        if end - cur_start > MAX_CHUNK_CHARS:
            flush()
            cur_start = start
            cur_end = end
        else:
            cur_end = end

    flush()
    return chunks


def _section_char_start(section: dict[str, Any]) -> int | None:
    for key in ("char_start", "start", "offset_start", "text_start"):
        try:
            value = section.get(key)
            if value is None:
                continue
            return int(value)
        except Exception:
            continue
    return None


def _split_section_text_for_chunks(
    text: str, *, section_kind: str
) -> list[tuple[int, int, str]]:
    txt = text or ""
    if not txt.strip():
        return []
    start, end = _trim_span(txt, 0, len(txt))
    txt = txt[start:end]

    # Abstracts are intentionally exported as one self-contained chunk.
    if section_kind == "abstract" or len(txt) <= MAX_CHUNK_CHARS:
        return [(0, len(txt), txt)]

    spans = _line_spans(txt)
    if not spans:
        return [(0, len(txt), txt)]
    return _pack_spans(txt, spans)


def _chunk_id(paper_id: str, section_key: str, chunk_index: int) -> str:
    key = re.sub(r"[^A-Za-z0-9_.:-]+", "-", section_key or "section").strip("-")
    key = key or "section"
    return f"{paper_id}:{key}:c{chunk_index:03d}"


def _compose_chunk_text(*, title: str, section_title: str, passage: str) -> str:
    parts: list[str] = []
    if title:
        parts.append(f"Paper: {title}")
    if section_title:
        parts.append(f"Section: {section_title}")
    if parts:
        parts.append("")
    parts.append((passage or "").strip())
    return "\n".join(parts).strip()


def _chunk_record(
    *,
    bundle: PaperBundle,
    section_kind: str,
    section_title: str,
    passage: str,
    source_artifact: str,
    source_section_id: str,
    char_start: int,
    char_end: int,
    section_key: str,
    chunk_index: int,
) -> dict[str, Any]:
    paper_id = bundle.capture_id
    title = bundle.title()
    return {
        "chunk_id": _chunk_id(paper_id, section_key, chunk_index),
        "paper_id": paper_id,
        "doi": bundle.doi(),
        "title": title,
        "year": _safe_year(bundle.year()),
        "authors": bundle.authors(),
        "section_kind": section_kind,
        "section_title": section_title,
        "text": _compose_chunk_text(
            title=title, section_title=section_title, passage=passage
        ),
        "source": {
            "capture_id": bundle.capture_id,
            "artifact": source_artifact,
            "section_id": source_section_id,
            "char_start": int(char_start),
            "char_end": int(char_end),
        },
    }


def chunks_jsonl_records(bundle: PaperBundle) -> list[dict[str, Any]]:
    """
    Canonical line shape for /exports/chunks.jsonl/.

    Emits retrieval-native evidence chunks from scientific structure rather than
    arbitrary paper-level blobs. References are intentionally excluded.
    """
    sections = bundle.standardized_sections()
    section_pairs = _sections_with_chunk_kinds(sections)
    has_section_abstract = any(kind == "abstract" for _section, kind in section_pairs)

    records: list[dict[str, Any]] = []

    if not has_section_abstract:
        abstract = standardize_text(str(bundle.reduced.get("abstract") or "")).strip()
        if abstract:
            records.append(
                _chunk_record(
                    bundle=bundle,
                    section_kind="abstract",
                    section_title="Abstract",
                    passage=abstract,
                    source_artifact="reduced.json",
                    source_section_id="",
                    char_start=0,
                    char_end=len(abstract),
                    section_key="abstract",
                    chunk_index=1,
                )
            )

    section_ordinal = 0
    for section, section_kind in section_pairs:
        section_ordinal += 1
        if section_kind in CHUNK_EXCLUDE_KINDS:
            continue
        if section_kind not in CHUNK_EVIDENCE_KINDS:
            continue

        text = standardize_text(str(section.get("text") or "")).strip()
        if not text:
            continue

        section_id = str(section.get("id") or "").strip()
        section_title = str(section.get("title") or "").strip()
        if not section_title and section_kind == "abstract":
            section_title = "Abstract"
        section_key = section_id or f"section-{section_ordinal:02d}"

        source_base = _section_char_start(section)
        for idx, (char_start, char_end, passage) in enumerate(
            _split_section_text_for_chunks(text, section_kind=section_kind), start=1
        ):
            source_char_start = (
                source_base + char_start if source_base is not None else char_start
            )
            source_char_end = (
                source_base + char_end if source_base is not None else char_end
            )
            records.append(
                _chunk_record(
                    bundle=bundle,
                    section_kind=section_kind,
                    section_title=section_title,
                    passage=passage,
                    source_artifact="sections.json",
                    source_section_id=section_id,
                    char_start=source_char_start,
                    char_end=source_char_end,
                    section_key=section_key,
                    chunk_index=idx,
                )
            )

    return records


def papers_jsonl_record(bundle: PaperBundle) -> dict[str, Any]:
    """
    Canonical line shape for /exports/papers.jsonl/.

    Keep this stable; future schema changes should happen HERE.
    """
    return {
        # Identity
        "id": bundle.capture_id,
        # Provenance/time (super useful in GPT uploads)
        "captured_at": bundle.captured_at(),
        "published_date_raw": bundle.published_date_raw(),
        # Core bibliographic-ish fields
        "title": bundle.title(),
        "doi": bundle.doi(),
        "url": bundle.url(),
        "year": bundle.year(),
        "container_title": bundle.container_title(),
        "authors": bundle.authors(),
        # Parse provenance (small + stable)
        "parse_parser": bundle.parse_parser(),
        "parse_ok": bundle.parse_ok(),
        "capture_quality": bundle.capture_quality(),
        "blocked_reason": bundle.blocked_reason(),
        "confidence_fulltext": bundle.confidence_fulltext(),
        "used_for_index": bundle.used_for_index(),
        # Content
        "sections": filtered_sections_for_papers_jsonl(bundle.sections),
    }
