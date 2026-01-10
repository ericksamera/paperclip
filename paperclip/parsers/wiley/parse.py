from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from ..base import ParseResult
from .sections import wiley_sections_from_html

_DOI_RX = re.compile(r"10\.\d{4,9}/[^\s<>\"']+", re.I)
_WS_RX = re.compile(r"\s+")

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

_SKIP_SECTION_IDS = {
    "article-references-section-1",
    "cited-by",
    "citedby-section",
}


def _norm_space(s: str) -> str:
    return _WS_RX.sub(" ", (s or "").strip())


def _safe_decompose(tag: Tag) -> None:
    try:
        tag.decompose()
    except Exception:
        try:
            tag.clear()
        except Exception:
            pass


def _strip_noise(root: Tag) -> None:
    for t in root.find_all(list(_STRIP_TAGS)):
        if isinstance(t, Tag):
            _safe_decompose(t)


def _find_article_root(soup: BeautifulSoup) -> tuple[str, Tag | None]:
    # Wiley (Literatum) often:
    #   div.article__body > article
    # Your sample matches this.
    for sel in (
        "div.article__body article",
        "article.article",
        "article",
    ):
        t = soup.select_one(sel)
        if isinstance(t, Tag) and t.get_text(" ", strip=True):
            return f"selector:{sel}", t
    return "selector:none", None


def _extract_doi_from_ref_li(li: Tag) -> str:
    # Prefer hidden doi span if present
    doi_span = li.select_one("span.hidden.data-doi")
    if isinstance(doi_span, Tag):
        s = _norm_space(doi_span.get_text(" ", strip=True))
        if s:
            return s.lower()

    # Otherwise regex match in rendered text
    t = li.get_text(" ", strip=True) or ""
    m = _DOI_RX.search(t)
    if m:
        return m.group(0).lower()
    return ""


def _parse_references(article: Tag) -> tuple[str, str, list[dict[str, str]]]:
    """
    Wiley refs are commonly in:
      section.article-section__references  ul li[data-bib-id]
    Even if accordion is collapsed, li nodes are usually present.
    """
    refs_root = article.select_one("section.article-section__references")
    if not isinstance(refs_root, Tag):
        return "", "", []

    items: list[dict[str, str]] = []
    for li in refs_root.select("li[data-bib-id]"):
        if not isinstance(li, Tag):
            continue
        txt = _norm_space(li.get_text(" ", strip=True))
        if not txt:
            continue
        doi = _extract_doi_from_ref_li(li)
        items.append({"n": "", "text": txt, "doi": doi, "pubmed": ""})

    refs_html = '<div data-paperclip="references">' + str(refs_root) + "</div>"

    lines: list[str] = ["References"] if items else []
    for it in items:
        suffix = f" [DOI:{it['doi']}]" if it.get("doi") else ""
        lines.append(f"{it['text']}{suffix}")
    refs_text = "\n".join(lines).strip()

    return refs_html, refs_text, items


def parse_wiley(*, url: str, dom_html: str, head_meta: dict[str, Any]) -> ParseResult:
    if not (dom_html or "").strip():
        return ParseResult(
            ok=False,
            parser="wiley",
            capture_quality="suspicious",
            notes=["empty_dom_html"],
        )

    soup = BeautifulSoup(dom_html, "html.parser")
    hint, art0 = _find_article_root(soup)
    if not isinstance(art0, Tag):
        return ParseResult(
            ok=False,
            parser="wiley",
            capture_quality="suspicious",
            notes=["wiley_no_article_root"],
            selected_hint=hint,
        )

    # Detached copy for safe mutation
    art_soup = BeautifulSoup(str(art0), "html.parser")
    article = art_soup.find()
    if not isinstance(article, Tag):
        return ParseResult(
            ok=False,
            parser="wiley",
            capture_quality="suspicious",
            notes=["wiley_copy_failed"],
            selected_hint=hint,
        )

    _strip_noise(article)

    notes: list[str] = []
    meta: dict[str, Any] = {}

    # References (use original art0 so we don't lose anything from stripping)
    refs_html, refs_text, ref_items = _parse_references(art0)
    if ref_items:
        meta["references"] = ref_items
        meta["references_count"] = len(ref_items)
        notes.append("wiley_refs_extracted")
    else:
        notes.append("wiley_no_refs_found")

    # Sections from HTML (same approach as OUP/PMC)
    sections = wiley_sections_from_html(article)
    if sections:
        meta["sections"] = sections
        meta["sections_count"] = len(sections)
        notes.append("wiley_sections_from_html")

        # Deterministic article_text from sections
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
    else:
        article_text = _norm_space(article.get_text("\n", strip=True))
        notes.append("wiley_sections_fallback_text")

    article_html = '<div data-paperclip="article-body">' + str(article) + "</div>"

    if not article_text.strip():
        return ParseResult(
            ok=False,
            parser="wiley",
            capture_quality="suspicious",
            notes=["wiley_empty_article_text"] + notes,
            selected_hint=hint,
            references_html=refs_html,
            references_text=refs_text,
            meta=meta,
        )

    confidence = 0.75 if len(article_text) >= 2500 else 0.6
    if len(article_text) >= 7000:
        confidence = 0.9

    return ParseResult(
        ok=True,
        parser="wiley",
        capture_quality="ok",
        confidence_fulltext=float(confidence),
        selected_hint=hint,
        notes=notes,
        meta=meta,
        article_html=article_html,
        article_text=article_text,
        references_html=refs_html,
        references_text=refs_text,
    )
