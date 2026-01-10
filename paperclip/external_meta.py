from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _join_name(given: str, family: str) -> str:
    given = (given or "").strip()
    family = (family or "").strip()
    if given and family:
        return f"{given} {family}".strip()
    return (family or given or "").strip()


def _parse_crossref_authors(message: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for a in (
        (message.get("author") or []) if isinstance(message.get("author"), list) else []
    ):
        if not isinstance(a, dict):
            continue
        name = _join_name(_as_str(a.get("given")), _as_str(a.get("family")))
        if not name:
            name = _as_str(a.get("name")).strip()
        if name:
            out.append(name)

    # De-dupe (case-insensitive), preserve order
    seen: set[str] = set()
    deduped: list[str] = []
    for x in out:
        k = x.casefold()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(x)
    return deduped


def _crossref_works_url(doi: str) -> str:
    # DOI can include slashes; must be URL-encoded as a path segment.
    return "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")


def fetch_crossref_metadata(
    doi: str,
    *,
    timeout_s: float = 3.5,
    user_agent: str = "paperclip/0.1.0 (mailto:local@localhost)",
) -> dict[str, Any] | None:
    """
    Best-effort Crossref lookup. Returns a small dict or None.

    Output keys (when present):
      - source: "crossref"
      - title: str
      - container_title: str
      - published_date_raw: str
      - year: int | None
      - authors: list[str]
    """
    doi = (doi or "").strip().lower()
    if not doi:
        return None

    url = _crossref_works_url(doi)
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": user_agent,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError:
        return None
    except Exception:
        return None

    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None

    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, dict):
        return None

    # Title fields
    title = ""
    t = message.get("title")
    if isinstance(t, list) and t:
        title = _as_str(t[0]).strip()
    elif isinstance(t, str):
        title = t.strip()

    container_title = ""
    ct = message.get("container-title")
    if isinstance(ct, list) and ct:
        container_title = _as_str(ct[0]).strip()
    elif isinstance(ct, str):
        container_title = ct.strip()

    # Published date (Crossref is messy; choose a reasonable raw string + year)
    published_date_raw = ""
    year: int | None = None

    def _year_from_parts(parts: Any) -> int | None:
        if (
            not isinstance(parts, list)
            or not parts
            or not isinstance(parts[0], list)
            or not parts[0]
        ):
            return None
        try:
            y = int(parts[0][0])
            return y if 1500 <= y <= 2200 else None
        except Exception:
            return None

    issued = message.get("issued")
    if isinstance(issued, dict):
        parts = issued.get("date-parts")
        y = _year_from_parts(parts)
        if y is not None:
            year = y
            published_date_raw = str(y)

            # If month/day are available, build YYYY-MM-DD-ish
            try:
                dp0 = parts[0] if isinstance(parts, list) and parts else None
                if isinstance(dp0, list) and len(dp0) >= 2:
                    m = int(dp0[1])
                    if 1 <= m <= 12:
                        published_date_raw = f"{year:04d}-{m:02d}"
                        if len(dp0) >= 3:
                            d = int(dp0[2])
                            if 1 <= d <= 31:
                                published_date_raw = f"{year:04d}-{m:02d}-{d:02d}"
            except Exception:
                pass

    authors = _parse_crossref_authors(message)

    return {
        "source": "crossref",
        "title": title,
        "container_title": container_title,
        "published_date_raw": published_date_raw,
        "year": year,
        "authors": authors,
    }


def best_external_authors_for_doi(doi: str) -> tuple[list[str], dict[str, Any] | None]:
    """
    Returns (authors, provenance_dict_or_none).
    """
    meta = fetch_crossref_metadata(doi)
    if not meta:
        return [], None
    authors = meta.get("authors") if isinstance(meta.get("authors"), list) else []
    authors = [str(a).strip() for a in authors if str(a or "").strip()]
    if not authors:
        return [], meta
    return authors, meta
