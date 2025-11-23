from __future__ import annotations

from typing import Any, Mapping

from captures.models import Capture
from paperclip.utils import norm_doi


def ref_kwargs(
    r: Mapping[str, Any], *, capture: Capture, csl_ok: bool = True
) -> dict[str, Any]:
    """
    Normalize a raw reference mapping into kwargs for captures.Reference.

    Responsibilities:
    - Normalize DOI via paperclip.utils.norm_doi.
    - Coerce issued_year/year to a simple string.
    - Resolve container_title / journal field naming.
    - Ensure authors is always a list[str].
    - Optionally keep client-provided CSL; ignore site-parser CSL by default.
    """
    # Raw text (best-effort original)
    raw = str(r.get("raw") or "")

    # --- DOI ---
    doi_raw = str(r.get("doi") or "").strip()
    doi_norm = norm_doi(doi_raw)
    # Store the canonical DOI if we can; otherwise fall back to the raw string
    doi = doi_norm or doi_raw

    # --- Year ---
    # Accept either 'issued_year' or 'year' and coerce to a simple string
    year_val = r.get("issued_year", r.get("year", ""))
    if isinstance(year_val, (int, float)):
        try:
            issued_year = str(int(year_val))
        except Exception:
            issued_year = str(year_val)
    else:
        issued_year = str(year_val or "").strip()

    # --- Container / journal title ---
    container_title = ""
    for key in ("container_title", "container-title", "journal", "journal_title"):
        v = r.get(key)
        if v:
            container_title = str(v).strip()
            if container_title:
                break

    # --- Authors -> list[str] ---
    authors_raw = r.get("authors") or []
    if isinstance(authors_raw, (list, tuple, set)):
        authors = [str(a).strip() for a in authors_raw if str(a).strip()]
    elif isinstance(authors_raw, str):
        authors = [authors_raw.strip()] if authors_raw.strip() else []
    else:
        authors = []

    # --- CSL (client-provided only; site parsers generally shouldn't inject CSL) ---
    csl = r.get("csl") if (csl_ok and isinstance(r.get("csl"), dict)) else {}

    return {
        "capture": capture,
        "ref_id": str(r.get("id") or ""),
        "raw": raw,
        "doi": doi,
        "title": str(r.get("title") or ""),
        "issued_year": issued_year,
        "container_title": container_title,
        "authors": authors,
        "csl": csl,
        "volume": str(r.get("volume") or ""),
        "issue": str(r.get("issue") or ""),
        "pages": str(r.get("pages") or ""),
        "publisher": str(r.get("publisher") or ""),
        "issn": str(r.get("issn") or ""),
        "isbn": str(r.get("isbn") or ""),
        "bibtex": str(r.get("bibtex") or ""),
        "apa": str(r.get("apa") or ""),
        "url": str(r.get("url") or ""),
    }
