from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from ...htmlutil import strip_noise
from ..base import ParseResult
from ...sectionizer import build_sections_meta
from .sections import oup_sections_from_html

_REF_HEADING_RX = re.compile(r"^\s*references\s*$", re.I)
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
}


def _norm(s: str) -> str:
    return _WS_RX.sub(" ", (s or "").strip())


def _find_fulltext_root(soup: BeautifulSoup) -> tuple[str, Tag | None]:
    selectors = [
        'div#ContentTab div.widget-ArticleFulltext div.widget-items[data-widgetname="ArticleFulltext"]',
        "div#ContentTab div.widget-ArticleFulltext div.widget-items",
        "div.widget-ArticleFulltext div.widget-items",
        "div.widget-ArticleFulltext",
    ]
    for sel in selectors:
        t = soup.select_one(sel)
        if isinstance(t, Tag) and t.get_text(" ", strip=True):
            return f"selector:{sel}", t
    return "selector:none", None


def _find_references_container(soup_or_root: Tag) -> Tag | None:
    ref_list = soup_or_root.select_one("div.ref-list")
    if isinstance(ref_list, Tag) and len(ref_list.get_text(" ", strip=True)) > 200:
        return ref_list

    for h in soup_or_root.find_all(["h2", "h3"]):
        if not isinstance(h, Tag):
            continue
        ht = _norm(h.get_text(" ", strip=True))
        if ht and _REF_HEADING_RX.match(ht):
            sib = h.find_next_sibling()
            while isinstance(sib, Tag):
                cls = " ".join(sib.get("class") or []).lower()
                if "ref-list" in cls:
                    return sib
                sib = sib.find_next_sibling()
            break

    return None


def _parse_references(refs_root: Tag) -> tuple[str, list[dict[str, str]]]:
    items: list[dict[str, str]] = []

    for item in refs_root.select("div.js-splitview-ref-item"):
        if not isinstance(item, Tag):
            continue
        txt = _norm(item.get_text(" ", strip=True))
        if not txt:
            continue
        doi = ""
        m = _DOI_RX.search(txt)
        if m:
            doi = m.group(0).lower()
        items.append({"n": "", "text": txt, "doi": doi, "pubmed": ""})

    if not items:
        for rc in refs_root.select("div.ref-content"):
            if not isinstance(rc, Tag):
                continue
            txt = _norm(rc.get_text(" ", strip=True))
            if not txt:
                continue
            doi = ""
            m = _DOI_RX.search(txt)
            if m:
                doi = m.group(0).lower()
            items.append({"n": "", "text": txt, "doi": doi, "pubmed": ""})

    lines: list[str] = ["References"] if items else []
    for it in items:
        suffix = f" [DOI:{it['doi']}]" if it.get("doi") else ""
        lines.append(f"{it['text']}{suffix}")

    return "\n".join(lines).strip(), items


def parse_oup(*, url: str, dom_html: str, head_meta: dict[str, Any]) -> ParseResult:
    if not (dom_html or "").strip():
        return ParseResult(
            ok=False,
            parser="oup",
            capture_quality="suspicious",
            notes=["empty_dom_html"],
        )

    soup = BeautifulSoup(dom_html, "html.parser")

    hint, fulltext0 = _find_fulltext_root(soup)
    if not isinstance(fulltext0, Tag):
        return ParseResult(
            ok=False,
            parser="oup",
            capture_quality="suspicious",
            notes=["oup_no_fulltext_root"],
            selected_hint=hint,
        )

    # Detached copy
    ft_soup = BeautifulSoup(str(fulltext0), "html.parser")
    fulltext = ft_soup.find()
    if not isinstance(fulltext, Tag):
        return ParseResult(
            ok=False,
            parser="oup",
            capture_quality="suspicious",
            notes=["oup_copy_failed"],
            selected_hint=hint,
        )

    strip_noise(fulltext, strip_tags=_STRIP_TAGS)

    notes: list[str] = []
    meta: dict[str, Any] = {}

    # References: extract from the *original soup* (full page), not from widget-items
    refs_tag = _find_references_container(soup)
    refs_html = ""
    refs_text = ""
    if isinstance(refs_tag, Tag):
        refs_html = '<div data-paperclip="references">' + str(refs_tag) + "</div>"
        refs_soup = BeautifulSoup(refs_html, "html.parser")
        rr = refs_soup.find()
        if isinstance(rr, Tag):
            refs_text, items = _parse_references(rr)
            meta["references"] = items
            meta["references_count"] = len(items)
        notes.append("oup_refs_extracted")
    else:
        notes.append("oup_no_refs_found")

    # Sections from HTML (preferred)
    sections = oup_sections_from_html(fulltext)
    if sections:
        meta["sections"] = sections
        meta["sections_count"] = len(sections)
        notes.append("oup_sections_from_html")

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
        article_text = _norm(fulltext.get_text("\n", strip=True))
        meta.update(build_sections_meta(article_text))
        notes.append("oup_sections_fallback_text")

    article_html = '<div data-paperclip="article-fulltext">' + str(fulltext) + "</div>"

    if not article_text.strip():
        return ParseResult(
            ok=False,
            parser="oup",
            capture_quality="suspicious",
            notes=["oup_empty_article_text"] + notes,
            selected_hint=hint,
            references_html=refs_html,
            references_text=refs_text,
            meta=meta,
        )

    confidence = 0.75 if len(article_text) >= 2000 else 0.6
    if len(article_text) >= 6000:
        confidence = 0.9

    return ParseResult(
        ok=True,
        parser="oup",
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
