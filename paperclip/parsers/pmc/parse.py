from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from ...htmlutil import safe_decompose, strip_noise
from ...sectionizer import build_sections_meta
from ..base import ParseResult
from .sections import pmc_sections_from_html

_REF_HEADING_RX = re.compile(
    r"^\s*(references|bibliography|works cited|literature cited)\s*$", re.I
)
_DOI_RX = re.compile(r"10\.\d{4,9}/[^\s<>\"']+", re.I)

_STRIP_TAGS = {
    "script",
    "style",
    "noscript",
    "iframe",
    "form",
    "input",
    "button",
    "svg",
    "canvas",
    "nav",
    "header",
    "aside",
}

_MEDIA_TAGS = {"figure", "video", "audio", "source", "track", "picture"}


def _normalize(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _strip_noise_pmc(root: Tag) -> None:
    # Common stripping (tags)
    strip_noise(root, strip_tags=_STRIP_TAGS)

    # Courtesy footer / boilerplate (PMC specific)
    for sel in ("footer", ".courtesy-note"):
        for t in root.select(sel):
            if isinstance(t, Tag) and len(t.get_text(" ", strip=True)) < 1000:
                safe_decompose(t)


def _strip_media_blocks(root: Tag) -> int:
    removed = 0
    for t in root.find_all(list(_MEDIA_TAGS)):
        if isinstance(t, Tag):
            safe_decompose(t)
            removed += 1

    # "Open in a new tab" affordances are noise
    for a in root.find_all("a"):
        if not isinstance(a, Tag):
            continue
        txt = (a.get_text(" ", strip=True) or "").strip().lower()
        if txt == "open in a new tab" or "open in a new tab" in txt:
            parent = a.parent if isinstance(a.parent, Tag) else None
            if parent and len(parent.get_text(" ", strip=True)) < 160:
                safe_decompose(parent)
                removed += 1
            else:
                safe_decompose(a)
                removed += 1
    return removed


def _find_roots(soup: BeautifulSoup) -> tuple[str, Tag | None, Tag | None]:
    """
    Returns (hint, article_content_root, main_body_root)
    """
    ac = soup.select_one("section[aria-label='Article content']")
    if isinstance(ac, Tag) and ac.get_text(" ", strip=True):
        mb = ac.select_one("section.body.main-article-body")
        if isinstance(mb, Tag) and mb.get_text(" ", strip=True):
            return "pmc:article-content + main-body", ac, mb
        return "pmc:article-content", ac, None

    for sel in ("article", "main", "[role='main']", "#content", "#mc", "#main-content"):
        t = soup.select_one(sel)
        if isinstance(t, Tag) and t.get_text(" ", strip=True):
            return f"fallback:{sel}", t, t

    return "fallback:none", None, None


def _find_references_section(search_root: Tag) -> Tag | None:
    t = search_root.select_one("section.ref-list")
    if isinstance(t, Tag) and len(t.find_all("li")) >= 3:
        return t

    t = search_root.select_one("section[id^='ref-list']")
    if isinstance(t, Tag) and len(t.find_all("li")) >= 3:
        return t

    t = search_root.select_one("[id*='ref-list' i]")
    if isinstance(t, Tag) and len(t.find_all("li")) >= 3:
        return t

    for h in search_root.find_all(["h1", "h2", "h3", "h4"]):
        ht = _normalize(h.get_text(" ", strip=True))
        if ht and _REF_HEADING_RX.match(ht):
            anc: Tag | None = h
            for _ in range(10):
                if not anc or not isinstance(anc.parent, Tag):
                    break
                parent = anc.parent
                if (
                    parent.name in {"section", "div"}
                    and len(parent.find_all("li")) >= 3
                ):
                    return parent
                anc = parent
            return h.parent if isinstance(h.parent, Tag) else None

    return None


def _ref_number(li: Tag) -> str:
    lab = li.find("span", class_=re.compile(r"\blabel\b", re.I))
    if isinstance(lab, Tag):
        s = (lab.get_text(" ", strip=True) or "").strip().rstrip(".").strip()
        if s:
            return s
    return ""


def _ref_text(li: Tag) -> str:
    cite = li.find("cite")
    if isinstance(cite, Tag):
        return _normalize(cite.get_text(" ", strip=True))
    return _normalize(li.get_text(" ", strip=True))


def _extract_doi(li: Tag) -> str:
    for a in li.find_all("a"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        m = _DOI_RX.search(href)
        if m:
            return m.group(0).lower()
    t = li.get_text(" ", strip=True)
    m2 = _DOI_RX.search(t or "")
    return m2.group(0).lower() if m2 else ""


def _extract_pubmed(li: Tag) -> str:
    for a in li.find_all("a"):
        href = (a.get("href") or "").strip()
        if "pubmed.ncbi.nlm.nih.gov" in href:
            return href
    return ""


def _parse_references(refs_section: Tag) -> tuple[str, list[dict[str, str]]]:
    items: list[dict[str, str]] = []

    list_root = refs_section.select_one("ol.ref-list") or refs_section.select_one(
        "ul.ref-list"
    )
    scope = list_root if isinstance(list_root, Tag) else refs_section

    for li in scope.find_all("li"):
        if not isinstance(li, Tag):
            continue
        if li.find("cite") is None:
            continue

        text = _ref_text(li)
        if not text:
            continue

        n = _ref_number(li)
        doi = _extract_doi(li)
        pubmed = _extract_pubmed(li)
        items.append({"n": n, "text": text, "doi": doi, "pubmed": pubmed})

    heading = ""
    h = refs_section.find(["h1", "h2", "h3", "h4"])
    if isinstance(h, Tag):
        heading = _normalize(h.get_text(" ", strip=True))

    lines: list[str] = []
    if heading:
        lines.append(heading)

    for it in items:
        extra: list[str] = []
        if it.get("doi"):
            extra.append(f"DOI:{it['doi']}")
        if it.get("pubmed"):
            extra.append(f"PubMed:{it['pubmed']}")
        suffix = f" [{' · '.join(extra)}]" if extra else ""

        if it.get("n"):
            lines.append(f"{it['n']}. {it['text']}{suffix}")
        else:
            lines.append(f"{it['text']}{suffix}")

    return "\n".join(lines).strip(), items


def _build_body_text(root: Tag) -> str:
    """
    Avoid double-counting list items:
    - keep <p> always
    - skip <li> if it contains <p> descendants
    """
    parts: list[str] = []
    for node in root.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        if node.name == "li" and node.find("p") is not None:
            continue
        t = node.get_text(" ", strip=True)
        if not t:
            continue
        parts.append(_normalize(t))
    return "\n".join(parts).strip()


def _remove_subtree(t: Tag) -> None:
    safe_decompose(t)


def parse_pmc(*, url: str, dom_html: str, head_meta: dict[str, Any]) -> ParseResult:
    if not dom_html.strip():
        return ParseResult(
            ok=False,
            parser="pmc",
            capture_quality="suspicious",
            notes=["empty_dom_html"],
        )

    soup = BeautifulSoup(dom_html, "html.parser")
    hint, ac0, body0 = _find_roots(soup)
    if not isinstance(ac0, Tag):
        return ParseResult(
            ok=False, parser="pmc", capture_quality="suspicious", notes=["pmc_no_root"]
        )

    # Detached copies
    ac_soup = BeautifulSoup(str(ac0), "html.parser")
    ac = ac_soup.find()
    if not isinstance(ac, Tag):
        return ParseResult(
            ok=False,
            parser="pmc",
            capture_quality="suspicious",
            notes=["pmc_copy_failed"],
        )

    if isinstance(body0, Tag):
        body_soup = BeautifulSoup(str(body0), "html.parser")
        body = body_soup.find()
    else:
        body = ac

    if not isinstance(body, Tag):
        return ParseResult(
            ok=False,
            parser="pmc",
            capture_quality="suspicious",
            notes=["pmc_body_copy_failed"],
        )

    notes: list[str] = []
    meta: dict[str, Any] = {}

    _strip_noise_pmc(ac)
    if body is not ac:
        _strip_noise_pmc(body)

    # References (search in article content)
    refs_tag = _find_references_section(ac)
    refs_html = ""
    refs_text = ""
    if isinstance(refs_tag, Tag):
        refs_html = '<div data-paperclip="references">' + str(refs_tag) + "</div>"
        refs_soup = BeautifulSoup(refs_html, "html.parser")
        refs_root = refs_soup.find()
        if isinstance(refs_root, Tag):
            refs_text, items = _parse_references(refs_root)
            meta["references"] = items
            meta["references_count"] = len(items)
        notes.append("pmc_refs_extracted")
    else:
        notes.append("pmc_no_refs_found")

    # Body cleanup
    assoc = body.select_one("section.associated-data")
    if isinstance(assoc, Tag):
        _remove_subtree(assoc)
        notes.append("pmc_removed_associated_data")

    removed_media = _strip_media_blocks(body)
    if removed_media:
        notes.append(f"pmc_removed_media_blocks:{removed_media}")

    # Site-specific section extraction (preferred), fallback to text sectionizer
    sections = pmc_sections_from_html(body)
    if sections:
        meta["sections"] = sections
        meta["sections_count"] = len(sections)

        lines: list[str] = []
        for s in sections:
            title = str(s.get("title") or "").strip()
            txt = str(s.get("text") or "").strip()
            if title:
                lines.append(title)
            if txt:
                lines.append(txt)
            lines.append("")
        article_text = "\n".join(lines).strip()
        notes.append("pmc_sections_from_html")
    else:
        article_text = _build_body_text(body)
        if (article_text or "").strip():
            meta.update(build_sections_meta(article_text))
        notes.append("pmc_sections_fallback_text")

    article_html = '<div data-paperclip="article-body">' + str(body) + "</div>"

    if not (article_text or "").strip():
        return ParseResult(
            ok=False,
            parser="pmc",
            capture_quality="suspicious",
            selected_hint=hint,
            notes=["pmc_empty_article_text"] + notes,
        )

    confidence = 0.9 if len(article_text) >= 1200 else 0.65
    if confidence < 0.8:
        notes.append("pmc_short_text")

    return ParseResult(
        ok=True,
        parser="pmc",
        capture_quality="ok",
        blocked_reason="",
        confidence_fulltext=float(confidence),
        article_html=article_html,
        article_text=article_text,
        references_html=refs_html,
        references_text=refs_text,
        selected_hint=hint,
        score_breakdown={},
        notes=notes,
        meta=meta,
    )
