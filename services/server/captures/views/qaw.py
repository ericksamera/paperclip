# services/server/captures/views/qaw.py
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render

from analysis.text import STOP
from captures.models import Capture, Collection
from captures.reduced_view import read_reduced_view

# Reuse your existing text/semantic/hybrid search chooser from Library
from captures.views.library import _search_ids_for_query  # keeps behavior consistent

_WORD = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def _tokens(s: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(s or "") if w.lower() not in STOP]


def _abstract_or_preview(c: Capture, max_paras: int = 3) -> str:
    view = read_reduced_view(str(c.id)) or {}
    sec = view.get("sections") or {}
    abs_txt = (sec.get("abstract") or "").strip()
    if abs_txt:
        return abs_txt
    paras = sec.get("abstract_or_body") or []
    if isinstance(paras, list) and paras:
        return " ".join([str(p) for p in paras[:max_paras] if p]).strip()
    meta = c.meta or {}
    csl = c.csl or {}
    return (
        meta.get("abstract") or (csl.get("abstract") if isinstance(csl, dict) else "") or ""
    ).strip()


def _caps_in_collection(col: Collection | None) -> list[Capture]:
    if col is None:
        return list(Capture.objects.all().order_by("-created_at"))
    return list(col.captures.all().order_by("-created_at"))


def _year_int(y: str | int | None) -> int | None:
    try:
        return int(str(y))
    except Exception:
        return None


def _filter_by_year(caps: list[Capture], yr_min: int | None, yr_max: int | None) -> list[Capture]:
    out = []
    for c in caps:
        y = _year_int(
            c.year or (c.meta or {}).get("year") or (c.meta or {}).get("publication_year")
        )
        if y is None:
            continue
        if (yr_min is not None and y < yr_min) or (yr_max is not None and y > yr_max):
            continue
        out.append(c)
    return out


@dataclass
class SourceRow:
    id: str
    title: str
    year: str
    journal: str
    url: str


def _sources_rows(caps: list[Capture]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in caps:
        meta = c.meta or {}
        csl = c.csl or {}
        j = (
            meta.get("container_title")
            or meta.get("container-title")
            or meta.get("journal")
            or csl.get("container-title")
            or csl.get("container_title")
            or ""
        )
        out.append(
            {
                "id": str(c.id),
                "title": (c.title or meta.get("title") or c.url or "").strip() or "(Untitled)",
                "year": c.year or "",
                "journal": j,
                "url": c.url or "",
            }
        )
    return out


def _hist_by_year(caps: list[Capture]) -> list[dict[str, Any]]:
    counter: dict[int, int] = defaultdict(int)
    for c in caps:
        y = _year_int(
            c.year or (c.meta or {}).get("year") or (c.meta or {}).get("publication_year")
        )
        if y is not None:
            counter[y] += 1
    if not counter:
        return []
    years = sorted(counter.keys())
    mx = max(counter.values()) or 1
    return [
        {"label": str(y), "count": counter[y], "pct": round(counter[y] * 100 / mx)} for y in years
    ]


def _top_terms(texts: list[str], k: int = 12) -> list[str]:
    freq: Counter[str] = Counter()
    for t in texts:
        freq.update(_tokens(t))
    return [w for (w, _) in freq.most_common(k)]


# ------------------------------ “methods” intent ------------------------------
_METHOD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("qPCR / RT-qPCR", re.compile(r"\b(qpcr|rt[- ]?qpcr|real[- ]?time[- ]?pcr)\b", re.I)),
    ("PCR", re.compile(r"\bpolymerase chain reaction\b|\bpcr\b", re.I)),
    ("Whole-genome sequencing (WGS)", re.compile(r"\bwhole[- ]?genome sequenc|\bWGS\b", re.I)),
    ("16S rRNA sequencing", re.compile(r"\b16s\s*r?rna\b", re.I)),
    ("Metagenomics", re.compile(r"\bmetagenom", re.I)),
    ("Phylogenetic analysis/MLST", re.compile(r"\bphylogen(et)?ic|MLST\b", re.I)),
    (
        "Antimicrobial susceptibility (MIC, disc diffusion)",
        re.compile(r"\bMICs?\b|disc[- ]diffusion|kirby[- ]bauer|broth[- ]microdilution", re.I),
    ),
    ("Culture-based isolation", re.compile(r"\bcultur(?:e|ing)|CFU\b", re.I)),
    ("ELISA / immunoassay", re.compile(r"\belisa\b|immunoassay", re.I)),
    (
        "Microscopy (TEM/SEM)",
        re.compile(
            r"\b(TEM|SEM|transmission electron microscopy|scanning electron microscopy)\b", re.I
        ),
    ),
    ("In vitro experiments", re.compile(r"\bin\s+vitro\b", re.I)),
    ("In vivo / animal challenge", re.compile(r"\bin\s+vivo\b|challenge(?:\s+trial)?", re.I)),
    (
        "Field sampling / surveillance",
        re.compile(r"\bfield\s+sampling|surveillance|monitoring\b", re.I),
    ),
]

_STUDY_DESIGN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Randomized / controlled trial", re.compile(r"\brandomi[sz]ed|controlled trial", re.I)),
    ("Cohort", re.compile(r"\bcohort study\b", re.I)),
    ("Case-control", re.compile(r"\bcase[- ]control\b", re.I)),
    ("Cross-sectional", re.compile(r"\bcross[- ]sectional\b", re.I)),
    ("Systematic review", re.compile(r"\bsystematic review\b", re.I)),
    ("Meta-analysis", re.compile(r"\bmeta[- ]analysis\b", re.I)),
]


def _sections_text_for(c: Capture, titles_like: tuple[str, ...]) -> str:
    """
    Return concatenated text from reduced-view sections whose titles look like “Methods”.
    """
    view = read_reduced_view(str(c.id)) or {}
    nodes = (view.get("sections") or {}).get("sections") or []
    out: list[str] = []

    def walk(n: dict[str, Any]):
        title = (n.get("title") or "").strip().lower()
        if any(k in title for k in titles_like):
            for p in n.get("paragraphs") or []:
                if p:
                    out.append(str(p))
        for ch in n.get("children") or []:
            walk(ch)

    for n in nodes if isinstance(nodes, list) else []:
        walk(n)
    return " ".join(out)


def _collect_method_corpus(caps: list[Capture]) -> list[str]:
    texts: list[str] = []
    for c in caps:
        t = []
        # 1) Dedicated Methods sections if present
        t.append(
            _sections_text_for(
                c, ("method", "material", "experimental", "study design", "sampling")
            )
        )
        # 2) Abstract/preview as a backstop (some papers summarize the approach there)
        t.append(_abstract_or_preview(c, 5))
        # 3) Keywords can carry technique names
        meta = c.meta or {}
        kw = meta.get("keywords") or []
        if isinstance(kw, list) and kw:
            t.append(" ".join([str(k) for k in kw if k]))
        texts.append(" ".join([s for s in t if s]))
    return texts


def _score_patterns(
    texts: list[str], pats: list[tuple[str, re.Pattern[str]]]
) -> list[tuple[str, int]]:
    counts: dict[str, int] = defaultdict(int)
    for text in texts:
        for name, rx in pats:
            if rx.search(text):
                counts[name] += 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _intent_of(q: str) -> str:
    q = (q or "").lower()
    if re.search(
        r"\b(method|methodology|how (?:do|did|were|was) .* (?:study|measure|investigat))", q
    ):
        return "methods"
    return "general"


# ------------------------------ generic bullets ------------------------------
def _auto_bullets(texts: list[str]) -> dict[str, list[str]]:
    agree_kw = re.compile(
        r"\b(increase(?:s|d)?|associated|consistent|evidence\s+suggests?)\b", re.I
    )
    disagree_kw = re.compile(r"\b(contradict|mixed\s+results|however|inconsistent)\b", re.I)
    gap_kw = re.compile(
        r"\b(limited|few|lack|scarce|insufficient|randomi[sz]ed|longitudinal)\b", re.I
    )

    agreements, disagreements, gaps = [], [], []
    for t in texts[:80]:
        line = t.strip()
        if not line:
            continue
        if agree_kw.search(line):
            agreements.append(line)
        if disagree_kw.search(line):
            disagreements.append(line)
        if gap_kw.search(line):
            gaps.append(line)

    def _clean(xs: list[str]) -> list[str]:
        seen = set()
        out = []
        for x in xs:
            k = re.sub(r"\s+", " ", x).strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(re.sub(r"\s+", " ", x).strip())
        return out[:4]

    return {
        "agreements": _clean(agreements),
        "disagreements": _clean(disagreements),
        "gaps": _clean(gaps),
    }


def _build_trace(
    q: str,
    method: str,
    total: int,
    kept: int,
    yr_min: int | None,
    yr_max: int | None,
    top_terms: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "title": "Plan",
            "children": [
                {"title": "Interpret question", "note": f"User asked: “{q}”"},
                {"title": "Pick strategy", "note": f"Mode = {method} (text | semantic | hybrid)"},
            ],
        },
        {
            "title": "Retrieve",
            "children": [
                {"title": "Search corpus", "note": f"Matched {total} item(s) before filters"},
                {"title": "Filter scope", "note": f"Year range = {yr_min or '—'}-{yr_max or '—'}"},
                {"title": "Select sources", "note": f"Kept top {kept} sources"},
            ],
        },
        {
            "title": "Synthesize",
            "children": [
                {"title": "Tokenize & score", "note": f"Top terms: {', '.join(top_terms[:8])}"},
            ],
        },
        {
            "title": "Compose",
            "children": [
                {
                    "title": "Structure answer",
                    "note": "Direct answer (if intent) + summary blocks.",
                },
            ],
        },
    ]


def _respond_ok(payload: dict[str, Any]) -> JsonResponse:
    return JsonResponse({"ok": True, **payload})


def _respond_err(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


# ------------------------------ main view ------------------------------
def collection_qaw(request: HttpRequest, pk: int):
    col = get_object_or_404(Collection, pk=pk)

    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return _respond_err("invalid_json", 400)

        q = (data.get("q") or "").strip()
        if not q:
            return _respond_err("missing_question", 400)

        method = (data.get("method") or "hybrid").strip().lower()  # "text" | "semantic" | "hybrid"
        yr_min = data.get("year_min")
        yr_max = data.get("year_max")
        try:
            yr_min = int(yr_min) if yr_min not in (None, "", "null") else None
        except Exception:
            yr_min = None
        try:
            yr_max = int(yr_max) if yr_max not in (None, "", "null") else None
        except Exception:
            yr_max = None

        limit = int(data.get("limit") or 30)
        limit = max(5, min(100, limit))

        universe = _caps_in_collection(col)
        universe_map = {str(c.id): c for c in universe}

        ids_ranked = _search_ids_for_query(q, method)  # shared helper from Library
        ids_ranked = [pk for pk in ids_ranked if pk in universe_map]
        total_before_filters = len(ids_ranked)

        kept_caps = _filter_by_year([universe_map[pk] for pk in ids_ranked], yr_min, yr_max)
        kept_caps = kept_caps[:limit]

        texts = [_abstract_or_preview(c, 4) for c in kept_caps]
        top = _top_terms(texts, 12)
        hist_years = _hist_by_year(kept_caps)
        bullets = _auto_bullets(texts)
        trace = _build_trace(q, method, total_before_filters, len(kept_caps), yr_min, yr_max, top)

        # -------- intent routing (methods) --------
        intent = _intent_of(q)
        direct_answer: dict[str, Any] | None = None
        if intent == "methods":
            corpus = _collect_method_corpus(kept_caps)
            methods = _score_patterns(corpus, _METHOD_PATTERNS)
            designs = _score_patterns(corpus, _STUDY_DESIGN_PATTERNS)

            def _fmt(items: list[tuple[str, int]], k: int = 10) -> list[str]:
                return [f"{name} — {cnt}" for (name, cnt) in items[:k] if cnt > 0]

            direct_answer = {
                "title": "Methods used across these papers",
                "bullets": _fmt(methods, 10),
                "designs": _fmt(designs, 8),
            }

        # executive summary lines
        es = []
        if top:
            es.append("Key themes: " + ", ".join(top[:6]))
        if hist_years:
            yrs = [int(h["label"]) for h in hist_years]
            es.append(
                f"Coverage spans {min(yrs)}-{max(yrs)}; mode around "
                f"{max(hist_years, key=lambda h: h['count'])['label']}."
            )
        if len(kept_caps) < total_before_filters:
            es.append(f"Scoped to {len(kept_caps)} sources (from {total_before_filters} matches).")

        answer = {
            "question": q,
            "intent": intent,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "direct": direct_answer,
            "summary": {
                "executive": es,
                "agreements": bullets["agreements"],
                "disagreements": bullets["disagreements"],
                "gaps": bullets["gaps"],
                "coverage_by_year": hist_years,
            },
            "sources": _sources_rows(kept_caps),
            "trace": trace,
        }
        return _respond_ok({"answer": answer})

    # GET → render UI
    return render(
        request,
        "captures/qaw.html",
        {
            "collection": {"id": col.id, "name": col.name},
            "defaults": {"method": "hybrid", "year_min": None, "year_max": None, "limit": 30},
        },
    )
