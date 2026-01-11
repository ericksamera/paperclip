from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from ...htmlutil import strip_noise
from ...sectionizer import build_sections_meta
from ..base import ParseResult
from .sections import sciencedirect_sections_from_html

_REF_HEADING_RX = re.compile(
    r"^\s*(references|bibliography|works cited|literature cited)\s*$", re.I
)
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

_SKIP_CLASS_FRAGMENTS = (
    "banner-options",
    "social",
    "exportcitation",
    "addtomendeley",
    "issue-navigation",
    "copyright",
    "referencedarticles",
    "listarticles",
    "cited-by",
    "recommended",
    "related-content",
    "toolbar",
)


def _norm_space(s: str) -> str:
    return _WS_RX.sub(" ", (s or "").strip())


def _find_article_root(soup: BeautifulSoup) -> tuple[str, Tag | None]:
    for sel in ("article",):
        t = soup.select_one(sel)
        if isinstance(t, Tag) and t.get_text(" ", strip=True):
            return f"selector:{sel}", t
    return "selector:none", None


def _find_body_root(article: Tag) -> Tag | None:
    for sel in ("div#body", "div.Body#body", "div.Body"):
        t = article.select_one(sel)
        if isinstance(t, Tag) and t.get_text(" ", strip=True):
            return t
    return None


def _find_abstract_root(article: Tag) -> Tag | None:
    for sel in ("div#abstracts", "div.Abstracts#abstracts", "div.abstract"):
        t = article.select_one(sel)
        if isinstance(t, Tag) and t.get_text(" ", strip=True):
            if len(t.get_text(" ", strip=True)) > 120:
                return t
    return None


def _find_references_container(article: Tag) -> Tag | None:
    # Modern ScienceDirect commonly uses section.bibliography + ol.references
    for sel in ("section.bibliography", "ol.references"):
        t = article.select_one(sel)
        if isinstance(t, Tag) and len(t.get_text(" ", strip=True)) > 200:
            return t

    # Fallback: find a heading and take a following container
    for h in article.find_all(["h2", "h3", "h4"]):
        if not isinstance(h, Tag):
            continue
        ht = _norm_space(h.get_text(" ", strip=True))
        if ht and _REF_HEADING_RX.match(ht):
            sib = h.find_next_sibling()
            while isinstance(sib, Tag):
                if len(sib.get_text(" ", strip=True)) > 200:
                    return sib
                sib = sib.find_next_sibling()

    return None


def _extract_references(ref_root: Tag) -> tuple[str, str, list[dict[str, str]]]:
    items: list[dict[str, str]] = []

    lis = ref_root.select("ol.references > li")
    if not lis:
        lis = ref_root.find_all("li")

    for li in lis:
        if not isinstance(li, Tag):
            continue
        txt = _norm_space(li.get_text(" ", strip=True))
        if not txt or len(txt) < 40:
            continue
        doi = ""
        m = _DOI_RX.search(txt)
        if m:
            doi = m.group(0).lower()
        items.append({"n": "", "text": txt, "doi": doi, "pubmed": ""})

    refs_html = '<div data-paperclip="references">' + str(ref_root) + "</div>"

    lines: list[str] = []
    if items:
        lines.append("References")
        for it in items:
            suffix = f" [DOI:{it['doi']}]" if it.get("doi") else ""
            lines.append(f"{it['text']}{suffix}")
    refs_text = "\n".join(lines).strip()

    return refs_html, refs_text, items


def _build_body_text_from_sections(sections: list[dict[str, Any]]) -> str:
    out: list[str] = []
    for s in sections:
        title = str(s.get("title") or "").strip()
        txt = str(s.get("text") or "").strip()
        if title:
            out.append(title)
        if txt:
            out.append(txt)
        out.append("")
    return "\n".join(out).strip()


def _strip_mathjax(root: Tag) -> int:
    """
    ScienceDirect sometimes inlines MathJax as huge SVG/MathML blobs that destroy text output.
    strip_noise() won't remove these because they're large; remove explicitly.
    """
    removed = 0

    # Common MathJax containers
    for sel in (
        ".MathJax",
        ".MathJax_SVG",
        ".MathJax_Preview",
        ".MJX_Assistive_MathML",
        ".mjx-container",
        ".mjx-assistive",
        "[id^='MathJax-Element']",
    ):
        for t in root.select(sel):
            if isinstance(t, Tag):
                try:
                    t.decompose()
                except Exception:
                    try:
                        t.clear()
                    except Exception:
                        pass
                removed += 1

    # Also remove spans/divs whose class contains "mathjax" or starts with "mjx"
    for t in root.find_all(True):
        if not isinstance(t, Tag):
            continue
        cls = " ".join(t.get("class") or []).lower()
        if ("mathjax" in cls) or ("mjx" in cls.split()):
            try:
                t.decompose()
            except Exception:
                try:
                    t.clear()
                except Exception:
                    pass
            removed += 1

    return removed


def _is_bibliography_or_citedby(sec: Tag) -> bool:
    if not isinstance(sec, Tag):
        return False
    cls = " ".join(sec.get("class") or []).lower()
    sid = str(sec.get("id") or "").lower()
    if "bibliography" in cls:
        return True
    if "listarticles" in cls or "cited-by" in cls:
        return True
    if sid.startswith("aep-bibliography"):
        return True
    if sid.startswith("section-cited-by") or sid == "section-cited-by":
        return True
    return False


def _content_root_for_sections(article: Tag) -> Tag:
    """
    Build a synthetic container that includes the main body plus post-body content
    (e.g. Acknowledgments) but excludes bibliography + cited-by.

    This matches the ScienceDirect DOM you pasted:
      - <div id="body"> ... </div>
      - <section id="aep-acknowledgment-id..."> ... </section>
      - <section class="bibliography"...> References ... </section>
      - <div id="section-cited-by"> ... </div>
    """
    body = _find_body_root(article)

    container_soup = BeautifulSoup(
        '<div data-paperclip="sciencedirect-content"></div>', "html.parser"
    )
    container = container_soup.find()
    assert isinstance(container, Tag)

    # Always include the body (or fall back to the article)
    if isinstance(body, Tag):
        container.append(BeautifulSoup(str(body), "html.parser"))
    else:
        container.append(BeautifulSoup(str(article), "html.parser"))
        return container

    # Include sibling <section> blocks after body that are content (e.g. acknowledgments),
    # stopping before bibliography/cited-by.
    sib = body.find_next_sibling()
    while isinstance(sib, Tag):
        # bibliography / cited-by: stop (rest is non-core)
        if sib.name == "section" and _is_bibliography_or_citedby(sib):
            break
        if sib.get("id") and str(sib.get("id")).lower() in {"section-cited-by"}:
            break
        cls = " ".join(sib.get("class") or []).lower()
        if "copyright" in cls or "tail" in cls:
            sib = sib.find_next_sibling()
            continue

        # Keep contenty sections (have an h2/h3/h4 and some text)
        if sib.name == "section":
            if _is_bibliography_or_citedby(sib):
                break
            if (
                sib.find(["h2", "h3", "h4"]) is not None
                and len(sib.get_text(" ", strip=True)) > 80
            ):
                container.append(BeautifulSoup(str(sib), "html.parser"))

        sib = sib.find_next_sibling()

    return container


def parse_sciencedirect(
    *, url: str, dom_html: str, head_meta: dict[str, Any]
) -> ParseResult:
    if not dom_html.strip():
        return ParseResult(
            ok=False,
            parser="sciencedirect",
            capture_quality="suspicious",
            notes=["empty_dom_html"],
        )

    soup = BeautifulSoup(dom_html, "html.parser")
    hint, article0 = _find_article_root(soup)
    if not isinstance(article0, Tag):
        return ParseResult(
            ok=False,
            parser="sciencedirect",
            capture_quality="suspicious",
            notes=["sciencedirect_no_article_root"],
            selected_hint=hint,
        )

    # Detached copy (like PMC/OUP do)
    article_soup = BeautifulSoup(str(article0), "html.parser")
    article = article_soup.find()
    if not isinstance(article, Tag):
        return ParseResult(
            ok=False,
            parser="sciencedirect",
            capture_quality="suspicious",
            notes=["sciencedirect_copy_failed"],
            selected_hint=hint,
        )

    notes: list[str] = []
    meta: dict[str, Any] = {}

    strip_noise(
        article,
        strip_tags=_STRIP_TAGS,
        skip_class_fragments=_SKIP_CLASS_FRAGMENTS,
        skip_id_fragments=_SKIP_CLASS_FRAGMENTS,
        max_text_len=500,
    )

    removed_math = _strip_mathjax(article)
    if removed_math:
        notes.append(f"sciencedirect_removed_mathjax:{removed_math}")

    abstract = _find_abstract_root(article)

    # References
    refs_tag = _find_references_container(article)
    refs_html = ""
    refs_text = ""
    if isinstance(refs_tag, Tag):
        refs_html, refs_text, ref_items = _extract_references(refs_tag)
        if ref_items:
            meta["references"] = ref_items
            meta["references_count"] = len(ref_items)
            notes.append("sciencedirect_refs_extracted")
        else:
            notes.append("sciencedirect_refs_empty")
    else:
        notes.append("sciencedirect_no_refs_found")

    # Content root (body + post-body content like acknowledgments; excludes bibliography/cited-by)
    content_root = _content_root_for_sections(article)

    # Sections from HTML
    sections = sciencedirect_sections_from_html(
        body_root=content_root, abstract_root=abstract
    )
    if sections:
        meta["sections"] = sections
        meta["sections_count"] = len(sections)
        notes.append("sciencedirect_sections_from_html")
        article_text = _build_body_text_from_sections(sections)
    else:
        article_text = _norm_space(content_root.get_text("\n", strip=True))
        notes.append("sciencedirect_sections_missing_used_body_text")

    # Text-based fallback sectionizer (like PMC/OUP do)
    if not meta.get("sections") and article_text.strip():
        meta.update(build_sections_meta(article_text))
        notes.append("sciencedirect_sections_fallback_text")

    article_html = '<div data-paperclip="article-body">' + str(content_root) + "</div>"

    if not article_text.strip():
        return ParseResult(
            ok=False,
            parser="sciencedirect",
            capture_quality="suspicious",
            notes=["sciencedirect_empty_article_text"] + notes,
            selected_hint=hint,
            references_html=refs_html,
            references_text=refs_text,
            meta=meta,
        )

    confidence = 0.75 if len(article_text) >= 2500 else 0.6
    if len(article_text) >= 9000:
        confidence = 0.9

    return ParseResult(
        ok=True,
        parser="sciencedirect",
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
