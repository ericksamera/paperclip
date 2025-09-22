from __future__ import annotations
from typing import Dict, Any, List

def _fmt_authors(auths) -> str:
    out = []
    if isinstance(auths, list):
        for a in auths:
            if isinstance(a, dict):
                fam = a.get("family") or ""
                giv = a.get("given") or ""
                nm = (str(fam).strip() + ", " + str(giv).strip()).strip(", ").strip()
                if nm:
                    out.append(nm)
            elif isinstance(a, str):
                s = a.strip()
                if s:
                    out.append(s)
    return " and ".join([a for a in out if a])

def _csl_to_bibtex(csl: Dict[str, Any], fallback_key: str = "ref") -> str:
    if not isinstance(csl, dict) or not csl:
        return ""
    typ = csl.get("type") or "article"
    key = csl.get("id") or fallback_key
    fields = []
    title = csl.get("title") or ""
    cont = csl.get("container-title") or ""
    doi = csl.get("DOI") or ""
    year = None
    try:
        year = csl.get("issued", {}).get("date-parts", [[None]])[0][0]
    except Exception:
        year = None
    authors = _fmt_authors(csl.get("author") or [])
    if title: fields.append(("title", str(title)))
    if cont: fields.append(("journal", str(cont)))
    if authors: fields.append(("author", authors))
    if year: fields.append(("year", str(year)))
    if doi: fields.append(("doi", str(doi)))
    for k_from, k_to in [
        ("volume","volume"), ("issue","number"), ("page","pages"),
        ("URL","url"), ("publisher","publisher"), ("ISSN","issn")
    ]:
        v = csl.get(k_from) or csl.get(k_from.upper())
        if v: fields.append((k_to, str(v)))
    body = ",\n".join([f"  {k} = {{{v}}}" for k, v in fields])
    return f"@{typ}{{{key},\n{body}\n}}"

def aggregate_bib(docs: List[Dict[str, Any]]) -> str:
    seen = set()
    out = []
    for d in docs:
        for r in (d.get("references") or []):
            key = r.get("id") or r.get("ref_id") or r.get("doi") or r.get("raw")
            if not key or key in seen:
                continue
            seen.add(key)
            if r.get("bibtex"):
                bt = str(r.get("bibtex")).strip()
                if bt:
                    out.append(bt)
                continue
            csl = r.get("csl") or {}
            bt = _csl_to_bibtex(csl, fallback_key=str(key))
            if bt:
                out.append(bt)
    return "\n\n".join(out)
