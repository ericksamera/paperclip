# captures/views.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple
from urllib.parse import urlsplit

from django.contrib import messages
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import Capture


# ---------- helpers ----------

def _site_label(url: str) -> Tuple[str, str]:
    """
    Return (label, host) for a URL. Label is a friendly badge for Actions.
    """
    if not url:
        return ("", "")
    host = urlsplit(url).netloc.lower()
    # Friendly mapping
    if "pmc.ncbi.nlm.nih.gov" in host or "ncbi.nlm.nih.gov" in host:
        return ("PMC", host)
    if "biomedcentral.com" in host:
        return ("BMC", host)
    if "wiley" in host:
        return ("Wiley", host)
    if "sciencedirect.com" in host:
        return ("ScienceDirect", host)
    if "springer" in host or "springeropen.com" in host:
        return ("Springer", host)
    if "nature.com" in host:
        return ("Nature", host)
    if "plos.org" in host:
        return ("PLOS", host)
    if "doi.org" in host:
        return ("DOI", host)
    # Default: registrable-ish part
    core = host.split(":")[0]
    parts = core.split(".")
    if len(parts) >= 2:
        name = parts[-2].capitalize()
    else:
        name = core.capitalize()
    return (name, host)


def _norm(s: str | None) -> str:
    return (s or "").strip()


def _doi_url(doi: str | None) -> str | None:
    doi = _norm(doi)
    return f"https://doi.org/{doi}" if doi else None


def _authors_str(cap: Capture) -> str:
    """
    Build a compact "Family, G., Family2, G. et al." string
    from either meta.authors or csl.author.
    """
    a = (cap.meta or {}).get("authors") or (cap.csl or {}).get("author") or []
    names: List[str] = []
    if isinstance(a, list):
        for p in a:
            if isinstance(p, dict):
                fam = _norm(p.get("family") or p.get("last") or p.get("last_name") or p.get("name"))
                giv = _norm(p.get("given") or p.get("first"))
                if fam and giv:
                    names.append(f"{fam}, {giv[:1]}." if giv else fam)
                elif fam or giv:
                    names.append(fam or giv)
            elif isinstance(p, str):
                t = _norm(p)
                if t:
                    names.append(t)
    if not names:
        return ""
    head = ", ".join(names[:3])
    return head + (" et al." if len(names) > 3 else "")


def _abstract_text(cap: Capture) -> str:
    return _norm((cap.csl or {}).get("abstract") or (cap.meta or {}).get("abstract"))


@dataclass
class Row:
    id: str
    idx: int
    title: str
    authors: str
    year: str
    journal: str
    doi: str
    doi_url: str | None
    url: str
    site_label: str
    site_host: str
    added: str  # yyyy-mm-dd
    refs: int
    abstract: str


def _build_rows(qs: List[Capture]) -> List[Row]:
    rows: List[Row] = []
    for i, c in enumerate(qs, start=1):
        meta = c.meta or {}
        journal = _norm(meta.get("container_title") or "")
        year = _norm(c.year)
        label, host = _site_label(c.url)
        doi = _norm(c.doi or meta.get("doi") or "")
        rows.append(
            Row(
                id=str(c.id),
                idx=i,
                title=_norm(c.title or meta.get("title") or c.url),
                authors=_authors_str(c),
                year=year or "—",
                journal=journal or "—",
                doi=doi or "—",
                doi_url=_doi_url(doi),
                url=c.url,
                site_label=label,
                site_host=host,
                added=c.created_at.date().isoformat(),
                refs=getattr(c, "ref_count", 0),
                abstract=_abstract_text(c),
            )
        )
    return rows


def _facet_counts(qs: List[Capture]) -> Dict[str, List[Tuple[str, int]]]:
    years: Dict[str, int] = {}
    journals: Dict[str, int] = {}
    sites: Dict[str, int] = {}

    for c in qs:
        meta = c.meta or {}
        y = _norm(c.year)
        if y:
            years[y] = years.get(y, 0) + 1

        j = _norm(meta.get("container_title") or "")
        if j:
            journals[j] = journals.get(j, 0) + 1

        label, _ = _site_label(c.url)
        if label:
            sites[label] = sites.get(label, 0) + 1

    def top(d: Dict[str, int], n=30):
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:n]

    return {"years": top(years), "journals": top(journals), "sites": top(sites)}


# ---------- views ----------

from django.views.generic import TemplateView

class LibraryView(TemplateView):
    template_name = "captures/list.html"

    # GET /library/?q=...&sort=added|title|year|journal|doi|refs&dir=asc|desc&year=YYYY&journal=...&site=PMC
    def get(self, request: HttpRequest) -> HttpResponse:
        q = _norm(request.GET.get("q"))
        sort = request.GET.get("sort") or "added"
        direction = request.GET.get("dir") or "desc"
        filter_year = _norm(request.GET.get("year"))
        filter_journal = _norm(request.GET.get("journal"))
        filter_site = _norm(request.GET.get("site"))

        qs = (
            Capture.objects.all()
            .annotate(ref_count=Count("references"))
            .order_by("-created_at")
        )

        # search
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(url__icontains=q)
                | Q(doi__icontains=q)
                | Q(meta__container_title__icontains=q)
            )

        # basic facet filters
        if filter_year:
            qs = qs.filter(year=filter_year)
        if filter_journal:
            qs = qs.filter(meta__container_title=filter_journal)
        if filter_site:
            # site filter by host or label match
            ids = []
            for c in qs:
                label, host = _site_label(c.url)
                if filter_site.lower() in (label.lower(), host.lower()):
                    ids.append(c.id)
            qs = qs.filter(id__in=ids)

        data = list(qs)
        facets = _facet_counts(data)

        # sorting in Python (mix of DB + JSON fields)
        def key_added(c: Capture): return c.created_at
        def key_title(c: Capture): return _norm(c.title or (c.meta or {}).get("title") or c.url).lower()
        def key_year(c: Capture): return _norm(c.year)
        def key_journal(c: Capture): return _norm((c.meta or {}).get("container_title") or "")
        def key_doi(c: Capture): return _norm(c.doi or (c.meta or {}).get("doi") or "")
        def key_refs(c: Capture): return getattr(c, "ref_count", 0)

        sort_map = {
            "added": key_added,
            "title": key_title,
            "year": key_year,
            "journal": key_journal,
            "doi": key_doi,
            "refs": key_refs,
        }
        keyfn = sort_map.get(sort, key_added)
        data.sort(key=keyfn, reverse=(direction == "desc"))

        rows = _build_rows(data)

        context = {
            "rows": rows,
            "q": q,
            "count": len(rows),
            "sort": sort,
            "dir": direction,
            "facets": facets,
            "selected": {"year": filter_year, "journal": filter_journal, "site": filter_site},
            "current_params": {k: v for k, v in request.GET.items()},
        }
        return render(request, self.template_name, context)


def capture_delete(request: HttpRequest, pk: str) -> HttpResponse:
    cap = get_object_or_404(Capture, pk=pk)
    if request.method == "POST":
        cap.delete()
        messages.success(request, "Deleted.")
        target = reverse("library")
        # keep current filters/sort if present
        if request.GET:
            target = f"{target}?{request.GET.urlencode()}"
        return redirect(target)
    return redirect("library")


def capture_open(request: HttpRequest, pk: str) -> HttpResponse:
    """Redirect the user to the original URL of the capture."""
    cap = get_object_or_404(Capture, pk=pk)
    return redirect(cap.url or "library")


def capture_view(request: HttpRequest, pk: str) -> HttpResponse:
    """Render the detail view for a single capture, including references and content."""
    cap = get_object_or_404(Capture, pk=pk)
    refs = cap.references.all().order_by("id")
    # Load the captured content HTML from artifacts to display in the detail template
    content_html = ""
    try:
        p = cap.artifact_path("content.html")
        if p.exists(): content_html = p.read_text(encoding="utf-8")
    except Exception:
        pass
    return render(request, "captures/detail.html", {"cap": cap, "refs": refs, "content": content_html})


def capture_artifact(request: HttpRequest, pk: str, basename: str) -> HttpResponse:
    """Serve an artifact file (HTML, JSON, etc.) from the capture's artifact directory."""
    cap = get_object_or_404(Capture, pk=pk)
    fp = cap.artifact_path(basename)
    if not fp.exists():
        raise Http404(f"Artifact not found: {basename}")
    if basename.endswith(".html"):
        ct = "text/html"
    elif basename.endswith(".json"):
        ct = "application/json"
    elif basename.endswith(".md"):
        ct = "text/markdown"
    else:
        ct = "application/octet-stream"
    return FileResponse(open(fp, "rb"), content_type=ct)
