from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from urllib.parse import quote

import requests  # type: ignore[import-untyped]
from django.conf import settings

if TYPE_CHECKING:
    from requests import Response  # pragma: no cover
else:  # pragma: no cover - runtime fallback when typing info unavailable
    Response = Any  # type: ignore[assignment]


DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")


def normalize_doi(candidate: str) -> Optional[str]:
    """Return a normalised DOI string when present."""

    if not candidate:
        return None

    text = candidate.strip()
    text = re.sub(r"(?i)^(https?://(dx\.)?doi\.org/)", "", text)
    text = re.sub(r"(?i)^doi:\s*", "", text)
    match = DOI_RE.search(text)
    return match.group(0).lower() if match else None


def first_str(value: Any) -> Optional[str]:
    """Return the first string entry from a list/sequence."""

    if isinstance(value, str):
        return value

    if isinstance(value, Sequence):
        for item in value:
            if isinstance(item, str):
                return item
    return None


def message_to_csl(message: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Crossref ``message`` payload into a CSL-like mapping."""

    if not isinstance(message, dict):
        message = {}

    authors: list[dict[str, str]] = []
    for entry in message.get("author") or []:
        family = (entry.get("family") or "").strip()
        given = (entry.get("given") or "").strip()
        if family or given:
            authors.append({"family": family, "given": given})

    issued = (
        message.get("issued")
        or message.get("published-print")
        or message.get("published-online")
        or {}
    )

    csl: Dict[str, Any] = {
        "type": message.get("type") or "article-journal",
        "title": first_str(message.get("title")),
        "container-title": first_str(message.get("container-title")),
        "author": authors,
        "issued": issued if isinstance(issued, dict) else {},
        "volume": message.get("volume"),
        "issue": message.get("issue"),
        "page": message.get("page"),
        "publisher": message.get("publisher"),
        "URL": message.get("URL"),
        "DOI": message.get("DOI"),
        "ISSN": message.get("ISSN"),
    }
    return {key: value for key, value in csl.items() if value not in (None, "", [])}


def csl_to_doc_meta(csl: Dict[str, Any]) -> Dict[str, Any]:
    """Map CSL metadata to the capture document meta shape."""

    meta: Dict[str, Any] = {}
    if not isinstance(csl, dict):
        return meta

    meta["title"] = csl.get("title")
    meta["journal"] = first_str(csl.get("container-title")) or csl.get("container_title")

    issued_year: Optional[str] = None
    issued = csl.get("issued") or {}
    date_parts = issued.get("date-parts") or issued.get("date_parts") or []
    if (
        isinstance(date_parts, list)
        and date_parts
        and isinstance(date_parts[0], (list, tuple))
        and date_parts[0]
    ):
        issued_year = str(date_parts[0][0])
    meta["issued_year"] = issued_year

    meta["volume"] = csl.get("volume")
    meta["issue"] = csl.get("issue")
    meta["pages"] = csl.get("page") or csl.get("pages")
    meta["publisher"] = csl.get("publisher")

    issn = csl.get("ISSN")
    if isinstance(issn, Sequence) and not isinstance(issn, (str, bytes)):
        issn = next((item for item in issn if isinstance(item, str)), None)
    meta["issn"] = issn

    doi = csl.get("DOI")
    meta["url"] = csl.get("URL") or (f"https://doi.org/{doi}" if doi else None)
    meta["authors"] = csl.get("author") or []
    if doi:
        meta["doi"] = doi

    return {key: value for key, value in meta.items() if value not in (None, "", [])}


def fetch_crossref(
    doi: str, timeout: float = 10.0
) -> Tuple[Optional[Dict[str, Any]], Optional[Response]]:
    """Fetch metadata from Crossref, returning the message payload when available."""

    doi_norm = normalize_doi(doi)
    if not doi_norm:
        return None, None

    url = f"https://api.crossref.org/works/{quote(doi_norm)}"
    params: Dict[str, str] = {}
    mail = getattr(settings, "CROSSREF_MAILTO", None)
    if mail:
        params["mailto"] = mail
    headers = {"User-Agent": f"paperclip/0.1 (+mailto:{mail})" if mail else "paperclip/0.1"}

    try:
        response: Response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException:
        return None, None

    if getattr(response, "status_code", None) == 200:
        try:
            payload = response.json()
        except ValueError:
            return None, response
        return payload.get("message"), response

    return None, response


def fetch_openalex(
    doi: str, timeout: float = 10.0
) -> Tuple[Optional[Dict[str, Any]], Optional[Response]]:
    """Fetch OpenAlex metadata for the supplied DOI."""

    doi_norm = normalize_doi(doi)
    if not doi_norm:
        return None, None

    url = f"https://api.openalex.org/works/doi:{doi_norm}"

    try:
        response: Response = requests.get(url, timeout=timeout)
    except requests.RequestException:
        return None, None

    if getattr(response, "status_code", None) == 200:
        try:
            payload = response.json()
        except ValueError:
            return None, response
        return payload, response

    return None, response


def openalex_to_csl(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a minimal OpenAlex record into CSL."""

    if not isinstance(obj, dict):
        obj = {}

    authors: list[dict[str, str]] = []
    for authorship in obj.get("authorships") or []:
        name = ((authorship.get("author") or {}).get("display_name") or "").strip()
        if not name:
            continue
        if "," in name:
            family, given = [part.strip() for part in name.split(",", 1)]
        else:
            parts = name.split()
            family = parts[-1] if parts else ""
            given = " ".join(parts[:-1]) if len(parts) > 1 else ""
        authors.append({"family": family, "given": given})

    host = obj.get("host_venue") or {}
    biblio = obj.get("biblio") or {}

    csl: Dict[str, Any] = {
        "type": "article-journal",
        "title": obj.get("title"),
        "container-title": host.get("display_name"),
        "author": authors,
        "issued": {"date-parts": [[obj.get("publication_year")]]} if obj.get("publication_year") else {},
        "volume": biblio.get("volume"),
        "issue": biblio.get("issue"),
        "page": _join_pages(biblio.get("first_page"), biblio.get("last_page")),
        "publisher": host.get("publisher"),
        "URL": (obj.get("primary_location", {}) or {}).get("landing_page_url")
        or (obj.get("ids", {}) or {}).get("openalex"),
        "DOI": normalize_doi(obj.get("doi") or (obj.get("ids", {}) or {}).get("doi") or ""),
        "ISSN": [host.get("issn_l")] if host.get("issn_l") else None,
    }
    return {key: value for key, value in csl.items() if value not in (None, "", [], {})}


def _join_pages(first_page: Any, last_page: Any) -> Optional[str]:
    """Join first/last page fields into a single range."""

    if not first_page and not last_page:
        return None
    if first_page and last_page:
        return f"{first_page}-{last_page}"
    return first_page or last_page


def enrich_from_doi(doi: str) -> Optional[Dict[str, Any]]:
    """Fetch CSL metadata for a DOI via Crossref/OpenAlex."""

    message, response = fetch_crossref(doi)
    if message:
        csl = message_to_csl(message)
        return {"source": "crossref", "csl": csl, "raw": message}

    record, _ = fetch_openalex(doi)
    if record:
        csl = openalex_to_csl(record)
        return {"source": "openalex", "csl": csl, "raw": record}

    return None
