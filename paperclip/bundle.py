from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paper_md import render_paper_markdown
from .text_standardize import standardize_text


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_json(p: Path) -> Any:
    try:
        return json.loads(_read_text(p))
    except Exception:
        return None


@dataclass(frozen=True)
class PaperBundle:
    """
    Best-effort loader for an on-disk capture bundle.

    Core artifacts:
      - reduced.json
      - sections.json
      - references.json
      - paper.md
    """

    capture_id: str
    cap_dir: Path

    reduced: dict[str, Any]
    sections: list[dict[str, Any]]
    references: list[dict[str, Any]]
    paper_md: str

    # Optional DB row as a fallback source for certain fields
    cap_row: dict[str, Any] | None = None

    @staticmethod
    def cap_dir_for(artifacts_root: Path, capture_id: str) -> Path:
        return artifacts_root / str(capture_id)

    @classmethod
    def load_best_effort(
        cls,
        *,
        artifacts_root: Path,
        capture_id: str,
        cap_row: dict[str, Any] | None = None,
    ) -> "PaperBundle":
        cap_id = str(capture_id or "").strip()
        cap_dir = cls.cap_dir_for(artifacts_root, cap_id)

        reduced: dict[str, Any] = {}
        sections: list[dict[str, Any]] = []
        references: list[dict[str, Any]] = []
        paper_md = ""

        if cap_dir.exists() and cap_dir.is_dir():
            v = _read_json(cap_dir / "reduced.json")
            if isinstance(v, dict):
                reduced = v

            v = _read_json(cap_dir / "sections.json")
            if isinstance(v, list):
                sections = [x for x in v if isinstance(x, dict)]

            v = _read_json(cap_dir / "references.json")
            if isinstance(v, list):
                references = [x for x in v if isinstance(x, dict)]

            txt = _read_text(cap_dir / "paper.md").rstrip()
            paper_md = (txt + "\n") if txt else ""

        return cls(
            capture_id=cap_id,
            cap_dir=cap_dir,
            reduced=reduced,
            sections=sections,
            references=references,
            paper_md=paper_md,
            cap_row=cap_row,
        )

    # ---- Convenience accessors (prefer reduced.json, fall back to DB row) ----

    def title(self) -> str:
        if self.reduced.get("title"):
            return str(self.reduced.get("title") or "")
        if self.cap_row:
            return str(self.cap_row.get("title") or "")
        return ""

    def doi(self) -> str:
        if self.reduced.get("doi"):
            return str(self.reduced.get("doi") or "")
        if self.cap_row:
            return str(self.cap_row.get("doi") or "")
        return ""

    def url(self) -> str:
        for k in ("source_url", "canonical_url"):
            v = self.reduced.get(k)
            if v:
                return str(v)
        if self.cap_row:
            return str(self.cap_row.get("url") or "")
        return ""

    def year(self) -> Any:
        if "year" in self.reduced:
            return self.reduced.get("year", None)
        if self.cap_row:
            return self.cap_row.get("year", None)
        return None

    def container_title(self) -> str:
        if self.reduced.get("container_title"):
            return str(self.reduced.get("container_title") or "")
        if self.cap_row:
            return str(self.cap_row.get("container_title") or "")
        return ""

    def authors(self) -> list[str]:
        v = self.reduced.get("authors")
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x or "").strip()]
        return []

    def published_date_raw(self) -> str:
        v = self.reduced.get("published_date_raw")
        if isinstance(v, str) and v.strip():
            return v.strip()
        return ""

    def captured_at(self) -> str:
        v = self.reduced.get("captured_at")
        if isinstance(v, str) and v.strip():
            return v.strip()
        # fallback to DB timestamps (not the same concept, but better than missing)
        if self.cap_row:
            for k in ("created_at", "updated_at"):
                vv = self.cap_row.get(k)
                if isinstance(vv, str) and vv.strip():
                    return vv.strip()
        return ""

    def parse_summary(self) -> dict[str, Any]:
        v = self.reduced.get("parse")
        return v if isinstance(v, dict) else {}

    def capture_quality(self) -> str:
        return str(self.parse_summary().get("capture_quality") or "")

    def confidence_fulltext(self) -> float:
        try:
            return float(self.parse_summary().get("confidence_fulltext") or 0.0)
        except Exception:
            return 0.0

    def parse_parser(self) -> str:
        return str(self.parse_summary().get("parser") or "")

    def parse_ok(self) -> bool:
        return bool(self.parse_summary().get("ok", False))

    def blocked_reason(self) -> str:
        return str(self.parse_summary().get("blocked_reason") or "")

    def used_for_index(self) -> bool:
        return bool(self.parse_summary().get("used_for_index", False))

    # ---- Artifact helpers ----

    def artifact_text(self, name: str, *, standardize: bool = False) -> str:
        if not name:
            return ""
        raw = _read_text(self.cap_dir / name)
        if not raw:
            return ""
        return standardize_text(raw) if standardize else raw

    def standardized_sections(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for s in self.sections:
            if not isinstance(s, dict):
                continue
            txt = standardize_text(str(s.get("text") or "")).strip()
            if not txt:
                continue
            s2 = dict(s)
            s2["text"] = txt
            out.append(s2)
        return out

    # ---- Paper markdown policy ----

    def synthesize_paper_md(self) -> str:
        title = (self.title() or "").strip()
        doi = (self.doi() or "").strip()
        container_title = (self.container_title() or "").strip()
        source_url = (self.url() or "").strip()

        year = self.year()
        year_i = int(year) if isinstance(year, int) else None

        article_text = self.artifact_text("article.txt", standardize=True).strip()
        refs_text = self.artifact_text("references.txt", standardize=True).strip()

        sections: list[dict[str, Any]] = []
        if article_text:
            sections = [
                {"id": "s01", "title": "Body", "kind": "other", "text": article_text}
            ]

        md = render_paper_markdown(
            title=title,
            source_url=source_url,
            doi=doi,
            container_title=container_title,
            year=year_i,
            sections=sections,
            references_text=refs_text,
        )
        return md or ""

    def best_paper_md(self) -> str:
        if (self.paper_md or "").strip():
            return self.paper_md.rstrip() + "\n"
        md = self.synthesize_paper_md().rstrip()
        return (md + "\n") if md else ""
