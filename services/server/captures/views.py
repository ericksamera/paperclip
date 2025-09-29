# services/server/captures/views.py
from __future__ import annotations
import io, json, shutil, zipfile
from typing import Any, Dict, List, Iterable
from urllib.parse import urlparse

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import (
    JsonResponse, HttpResponse, FileResponse, Http404, HttpResponseRedirect
)
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import View
from django.views.decorators.http import require_POST

from .models import Capture, Collection, Reference
from paperclip.journals import get_short_journal_name
from .xref import enrich_reference_via_crossref
from .search import search_ids  # FTS
from paperclip.artifacts import artifact_path

# ---------- helpers ----------
def _site_label(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.replace("www.", "") if host else ""
    except Exception:
        return ""

def _family_from_name(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if "," in s:
        fam = s.split(",", 1)[0].strip()
        return fam or s
    parts = [p for p in s.replace("·", " ").split() if p]
    return parts[-1] if parts else s

def _author_list(meta: dict, csl: dict) -> List[str]:
    names: List[str] = []
    if isinstance(meta, dict) and isinstance(meta.get("authors"), list):
        for a in meta["authors"]:
            if isinstance(a, str) and a.strip():
                names.append(a.strip())
            elif isinstance(a, dict):
                fam = (a.get("family") or a.get("last") or "").strip()
                giv = (a.get("given") or a.get("first") or "").strip()
                names.append(" ".join([t for t in (giv, fam) if t]))
    if isinstance(csl, dict) and isinstance(csl.get("author"), list):
        for a in csl["author"]:
            fam = (a.get("family") or a.get("last") or "").strip()
            giv = (a.get("given") or a.get("first") or "").strip()
            names.append(" ".join([t for t in (giv, fam) if t]))
    seen, out = set(), []
    for n in names:
        key = n.lower()
        if n and key not in seen:
            seen.add(key)
            out.append(n)
    return out

def _authors_intext(meta: dict, csl: dict) -> str:
    raw = _author_list(meta or {}, csl or {})
    if not raw:
        return ""
    fam = _family_from_name(raw[0])
    return fam if len(raw) == 1 else f"{fam} et al."

def _journal_full(meta: dict, csl: dict) -> str:
    meta = meta or {}; csl = csl or {}
    return (
        meta.get("container_title")
        or meta.get("container-title")
        or meta.get("journal")
        or csl.get("container-title")
        or csl.get("container_title")
        or ""
    )

def _doi_url(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi if doi.startswith("http://") or doi.startswith("https://") else f"https://doi.org/{doi}"

def _row(c: Capture) -> Dict[str, Any]:
    meta = c.meta or {}
    csl = c.csl or {}
    title = (c.title or meta.get("title") or csl.get("title") or c.url or "").strip() or "(Untitled)"
    authors_intext = _authors_intext(meta, csl)
    j_full = _journal_full(meta, csl)
    j_short = get_short_journal_name(j_full, csl)
    doi = (c.doi or meta.get("doi") or csl.get("DOI") or "").strip()
    keywords = meta.get("keywords") or []
    abstract = (meta.get("abstract") or (csl.get("abstract") if isinstance(csl, dict) else "")) or ""
    try:
        refs_count = c.references.count()
    except Exception:
        refs_count = 0
    return {
        "id": str(c.id),
        "title": title,
        "url": c.url or "",
        "site_label": _site_label(c.url or ""),
        "authors_intext": authors_intext,
        "journal": j_full,
        "journal_short": j_short or j_full,
        "year": c.year or meta.get("year") or meta.get("publication_year") or "",
        "doi": doi,
        "doi_url": _doi_url(doi),
        "keywords": keywords,
        "abstract": abstract,
        "added": c.created_at.strftime("%Y-%m-%d"),
        "refs": refs_count,
    }

def _apply_filters(qs: Iterable[Capture], *, year: str, journal: str, site: str, col: str) -> List[Capture]:
    out: List[Capture] = []
    for c in qs:
        meta = c.meta or {}; csl = c.csl or {}
        year_ok = (not year) or (str(c.year or "") == year)
        j = _journal_full(meta, csl).lower()
        journal_ok = (not journal) or (j == journal)
        s = (_site_label(c.url or "")).lower()
        site_ok = (not site) or (s == site)
        col_ok = True
        if col:
            col_ok = c.collections.filter(id=col).exists()
        if year_ok and journal_ok and site_ok and col_ok:
            out.append(c)
    return out

def _build_facets(all_caps: Iterable[Capture]) -> Dict[str, Any]:
    years: Dict[str, int] = {}
    journals: Dict[str, int] = {}
    sites: Dict[str, int] = {}
    for c in all_caps:
        if c.year:
            key = str(c.year)
            years[key] = years.get(key, 0) + 1
        j = _journal_full(c.meta or {}, c.csl or {})
        if j:
            journals[j] = journals.get(j, 0) + 1
        s = _site_label(c.url or "")
        if s:
            sites[s] = sites.get(s, 0) + 1
    yr_sorted = sorted(years.items(), key=lambda kv: int(kv[0]), reverse=True)
    max_count = (max(years.values()) if years else 1)
    years_hist = [{"label": y, "count": n, "pct": int(round(n * 100 / max_count))} for y, n in yr_sorted]
    def sort_desc(d: Dict[str, int]) -> List[tuple[str, int]]:
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"years": years_hist, "journals": sort_desc(journals), "sites": sort_desc(sites)}

def _collections_with_counts() -> List[Dict[str, Any]]:
    cols = Collection.objects.annotate(count=Count("captures")).order_by("name")
    return [{"id": c.id, "name": c.name, "count": c.count, "parent": c.parent_id} for c in cols]

# ---------- Library ----------
class LibraryView(View):
    template_name = "captures/list.html"

    def get(self, request):
        sort = (request.GET.get("sort") or "created_at").strip()
        direction = (request.GET.get("dir") or "desc").strip().lower()
        page_no = int(request.GET.get("page") or 1)
        per = int(request.GET.get("per") or 200)
        qterm = (request.GET.get("q") or "").strip()
        year = (request.GET.get("year") or "").strip()
        journal = (request.GET.get("journal") or "").strip().lower()
        site = (request.GET.get("site") or "").strip().lower()
        col = (request.GET.get("col") or "").strip()

        sort_map = {"title": "title", "year": "year", "created_at": "created_at", "journal": "created_at"}
        key = sort_map.get(sort, "created_at")
        order_by = f"-{key}" if direction == "desc" else key

        base_qs = Capture.objects.all().order_by(order_by)
        facets = _build_facets(base_qs)
        collections = _collections_with_counts()

        if qterm:
            ids = search_ids(qterm)
            rank = {pk: i for i, pk in enumerate(ids)}
            fts_qs = Capture.objects.filter(id__in=ids)
            filtered = _apply_filters(fts_qs, year=year, journal=journal, site=site, col=col)
            filtered.sort(key=lambda c: rank.get(str(c.id), 10**9))
            total = len(filtered)
            start, end = (page_no - 1) * per, (page_no - 1) * per + per
            rows = [_row(c) for c in filtered[start:end]]
            return render(request, self.template_name, {
                "rows": rows, "count": total, "sort": sort, "dir": direction,
                "current_params": request.GET,
                "selected": {"q": qterm, "year": year, "journal": journal, "site": site, "col": col},
                "facets": facets, "collections": collections,
            })

        filtered = _apply_filters(base_qs, year=year, journal=journal, site=site, col=col)
        paginator = Paginator(filtered, per)
        page = paginator.get_page(page_no)
        rows = [_row(c) for c in page.object_list]
        return render(request, self.template_name, {
            "rows": rows, "count": paginator.count, "sort": sort, "dir": direction,
            "current_params": request.GET,
            "selected": {"q": qterm, "year": year, "journal": journal, "site": site, "col": col},
            "facets": facets, "collections": collections,
        })

# ---------- Collection CRUD + Assign ----------
@require_POST
def collection_create(request):
    name = (request.POST.get("name") or "").strip()
    parent_id = request.POST.get("parent") or None
    if not name:
        return redirect("library")
    parent = Collection.objects.filter(pk=parent_id).first() if parent_id else None
    col = Collection.objects.create(name=name, parent=parent)
    return redirect(f"{reverse('library')}?col={col.id}")

@require_POST
def collection_rename(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    name = (request.POST.get("name") or "").strip()
    if name:
        col.name = name
        col.save(update_fields=["name"])
    return redirect(f"{reverse('library')}?col={col.id}")

@require_POST
def collection_delete(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    col.delete()
    return redirect("library")

@require_POST
def collection_assign(request, pk: int):
    col = get_object_or_404(Collection, pk=pk)
    op = (request.POST.get("op") or "add").lower()
    ids = request.POST.getlist("ids")
    if not ids:
        return redirect(f"{reverse('library')}?col={col.id}")
    qs = Capture.objects.filter(id__in=ids)
    if op == "remove":
        col.captures.remove(*qs)
    else:
        col.captures.add(*qs)
    return redirect(f"{reverse('library')}?col={col.id}")

def collection_download_views(request, cid: str):
    """
    Download a zip of all view.json files for the current collection (or 'all').
    """
    if cid == "all":
        caps = Capture.objects.all()
        label = "all-items"
    else:
        col = get_object_or_404(Collection, pk=int(cid))
        caps = col.captures.all()
        label = f"collection-{col.id}"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in caps:
            p = artifact_path(str(c.id), "view.json")
            if p.exists():
                # use a readable stable filename
                safe_title = (c.title or str(c.id))[:60].replace("/", "_").replace("\\", "_")
                zf.write(p, arcname=f"{safe_title}__{c.id}_view.json")
    buf.seek(0)
    resp = HttpResponse(buf.read(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{label}-views.zip"'
    return resp

# ---------- Dedup review ----------
def _dupes_path() -> tuple[io.TextIOWrapper, str]:
    # helper only; not used directly
    pass

def _read_dupes() -> List[List[str]]:
    p = settings.ANALYSIS_DIR / "dupes.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("groups") or []
    except Exception:
        return []

def _ignored_set() -> set[str]:
    p = settings.ANALYSIS_DIR / "dupes_ignored.json"
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(data.get("ignored") or [])
    except Exception:
        return set()

def _write_ignored(s: set[str]) -> None:
    p = settings.ANALYSIS_DIR / "dupes_ignored.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ignored": sorted(s)}, indent=2), encoding="utf-8")

def _group_key(ids: List[str]) -> str:
    return ",".join(sorted(ids))

def dedup_review(request):
    groups = _read_dupes()
    ignored = _ignored_set()
    show_all = request.GET.get("all") == "1"
    vis_groups: List[List[str]] = []
    for g in groups:
        key = _group_key(g)
        if not show_all and key in ignored:
            continue
        vis_groups.append(g)

    # decorate with capture rows
    decorated = []
    for g in vis_groups:
        rows = []
        for pk in g:
            c = Capture.objects.filter(pk=pk).first()
            if not c:
                continue
            rows.append({
                "id": str(c.id),
                "title": c.title or "(Untitled)",
                "doi": c.doi or "",
                "year": c.year or "",
                "journal": _journal_full(c.meta or {}, c.csl or {}),
            })
        if len(rows) > 1:
            decorated.append(rows)

    return render(request, "captures/dupes.html", {
        "groups": decorated,
        "ignored_count": len(ignored),
        "all_mode": show_all,
    })

@require_POST
def dedup_scan_view(_request):
    # quick in-process scan; identical to management command
    from captures.dedup import find_near_duplicates
    groups = find_near_duplicates(threshold=0.85)
    p = settings.ANALYSIS_DIR / "dupes.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"groups": groups}, indent=2), "utf-8")
    return redirect("dedup_review")

@require_POST
def dedup_ignore(request):
    ids = request.POST.getlist("ids")
    if not ids:
        return redirect("dedup_review")
    ignored = _ignored_set()
    ignored.add(_group_key(ids))
    _write_ignored(ignored)
    return redirect("dedup_review")

@require_POST
def dedup_merge(request):
    primary_id = request.POST.get("primary")
    others = request.POST.getlist("others")
    if not primary_id or not others:
        return redirect("dedup_review")

    primary = get_object_or_404(Capture, pk=primary_id)
    # merge inside a transaction
    with transaction.atomic():
        for oid in others:
            if oid == primary_id:
                continue
            dup = Capture.objects.filter(pk=oid).first()
            if not dup:
                continue
            # 1) move references
            Reference.objects.filter(capture_id=dup.id).update(capture=primary)
            # 2) move collections
            for col in dup.collections.all():
                col.captures.add(primary)
            # 3) delete dup row
            dup.delete()
            # 4) remove dup artifacts folder
            try:
                shutil.rmtree((settings.ARTIFACTS_DIR / str(oid)), ignore_errors=True)
            except Exception:
                pass

    # mark this group as handled (ignored)
    ignored = _ignored_set()
    ids = [primary_id] + others
    ignored.add(_group_key(ids))
    _write_ignored(ignored)

    return redirect("dedup_review")

# ---------- passthrough unchanged views (detail/export/etc.) ----------
def library_page(request):  # lightweight JSON paging helper
    per = int(request.GET.get("per") or 200)
    page_no = int(request.GET.get("page") or 1)
    qs = Capture.objects.all().order_by("-created_at")
    year = (request.GET.get("year") or "").strip()
    journal = (request.GET.get("journal") or "").strip().lower()
    site = (request.GET.get("site") or "").strip().lower()
    col = (request.GET.get("col") or "").strip()
    filtered = _apply_filters(qs, year=year, journal=journal, site=site, col=col)
    paginator = Paginator(filtered, per)
    page = paginator.get_page(page_no)
    rows = [_row(c) for c in page.object_list]
    return JsonResponse({
        "rows": rows,
        "page": {
            "total": paginator.count,
            "per": per,
            "page": page.number,
            "has_next": page.has_next(),
            "next_page": page.next_page_number() if page.has_next() else None,
        }
    })

def capture_view(request, pk):
    cap = get_object_or_404(Capture, pk=pk)
    content = ""
    p = artifact_path(str(cap.id), "content.html")
    if p.exists():
        content = p.read_text(encoding="utf-8")
    csl = cap.csl if isinstance(csl := cap.csl, dict) else {}
    abs_text = (cap.meta or {}).get("abstract") or csl.get("abstract") or ""
    refs = cap.references.all().order_by("id")
    return render(request, "captures/detail.html", {"cap": cap, "content": content, "refs": refs, "abs": abs_text})

def capture_open(request, pk):
    cap = get_object_or_404(Capture, pk=pk)
    if not cap.url:
        return HttpResponse("No URL for this capture", status=404)
    return HttpResponseRedirect(cap.url)

def capture_delete(request, pk):
    if request.method != "POST":
        return HttpResponse(status=405)
    cap = get_object_or_404(Capture, pk=pk)
    cap.delete()
    return redirect("library")

def capture_bulk_delete(request):
    if request.method != "POST":
        return HttpResponse(status=405)
    ids = request.POST.getlist("ids")
    if ids:
        Capture.objects.filter(id__in=ids).delete()
    return redirect("library")

def capture_enrich_refs(request, pk):
    if request.method != "POST":
        return HttpResponse(status=405)
    cap = get_object_or_404(Capture, pk=pk)
    for r in cap.references.all().order_by("id"):
        try:
            upd = enrich_reference_via_crossref(r)
        except Exception:
            upd = None
        if upd:
            for k, v in upd.items():
                setattr(r, k, v)
            r.save(update_fields=list(upd.keys()))
    return redirect("capture_view", pk=str(cap.id))

def capture_export(request):
    import csv
    from io import StringIO
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id","title","authors_intext","year","journal_short","doi","url"])
    for c in Capture.objects.all().order_by("-created_at"):
        meta = c.meta or {}; csl = c.csl or {}
        title = (c.title or meta.get("title") or csl.get("title") or c.url or "").strip() or "(Untitled)"
        authors = _authors_intext(meta, csl)
        j_full = _journal_full(meta, csl)
        j_short = get_short_journal_name(j_full, csl) or j_full
        doi = (c.doi or meta.get("doi") or csl.get("DOI") or "").strip()
        w.writerow([str(c.id), title, authors, c.year, j_short, doi, c.url or ""])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="paperclip_export.csv"'
    return resp

def capture_artifact(request, pk, basename: str):
    cap = get_object_or_404(Capture, pk=pk)
    p = artifact_path(str(cap.id), basename)
    if not p.exists():
        raise Http404("Artifact not found")
    if p.suffix in {".json", ".html", ".txt"}:
        return FileResponse(open(p, "rb"), content_type="text/plain; charset=utf-8")
    return FileResponse(open(p, "rb"))
