from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from ..sectionizer import build_sections_meta
from .base import ParseResult

_WALL_PATTERNS = [
    (re.compile(r"\bcookie(s)?\b.*\b(consent|preferences)\b", re.I), "cookie_wall"),
    (re.compile(r"\b(consent|gdpr)\b", re.I), "cookie_wall"),
    (
        re.compile(r"\bsubscribe\b|\bsubscription\b|\bsign in\b|\blog in\b", re.I),
        "paywall",
    ),
    (re.compile(r"\bactivate\b.*\bsubscription\b", re.I), "paywall"),
    (
        re.compile(r"\bunusual traffic\b|\bare you a robot\b|\bcaptcha\b", re.I),
        "bot_block",
    ),
]

_SECTIONY_WORDS = re.compile(
    r"\b(abstract|introduction|methods?|materials?|results?|discussion|conclusion|references)\b",
    re.I,
)

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
    "footer",
    "aside",
}

_REF_HEADING_RX = re.compile(
    r"^\s*(references|bibliography|works cited|literature cited|citations)\s*$", re.I
)


def _text_len(tag: Tag) -> int:
    return len(tag.get_text(" ", strip=True))


def _link_text_len(tag: Tag) -> int:
    total = 0
    for a in tag.find_all("a"):
        total += len(a.get_text(" ", strip=True))
    return total


def _paragraph_count(tag: Tag) -> int:
    return len(tag.find_all("p"))


def _heading_count(tag: Tag) -> int:
    return len(tag.find_all(["h1", "h2", "h3", "h4"]))


def _strip_noise(tag: Tag) -> None:
    for t in tag.find_all(list(_STRIP_TAGS)):
        try:
            t.decompose()
        except Exception:
            pass

    for bad in tag.find_all(True):
        try:
            if not isinstance(bad, Tag):
                continue
            cls_val = bad.get("class")
            if isinstance(cls_val, list):
                cls = " ".join([str(x) for x in cls_val if x is not None])
            elif isinstance(cls_val, str):
                cls = cls_val
            else:
                cls = ""
            bid = bad.get("id")
            bid = bid if isinstance(bid, str) else ""

            hay = f"{cls} {bid}".lower()
            if any(
                k in hay
                for k in (
                    "nav",
                    "breadcrumb",
                    "toolbar",
                    "cookie",
                    "consent",
                    "subscribe",
                    "paywall",
                    "header",
                    "footer",
                    "sidebar",
                    "related",
                    "recommend",
                    "advert",
                    "promo",
                )
            ):
                if _text_len(bad) < 400:
                    try:
                        bad.decompose()
                    except Exception:
                        pass
        except Exception:
            continue


def _detect_wall(soup: BeautifulSoup) -> tuple[str, str, list[str]]:
    text = soup.get_text(" ", strip=True)
    if not text:
        return "suspicious", "unknown", ["empty_document_text"]

    hits: list[str] = []
    reason = ""
    for rx, r in _WALL_PATTERNS:
        if rx.search(text):
            hits.append(rx.pattern)
            reason = r
            break

    if not reason and re.search(
        r"\b(accept|reject|manage)\b.*\b(cookie|consent)\b", text, re.I
    ):
        reason = "cookie_wall"
        hits.append("accept/reject/manage cookie")

    if reason:
        if len(text) < 4000:
            return "blocked", reason, hits
        return "suspicious", reason, hits

    if len(text) < 800:
        return "suspicious", "", ["very_short_document_text"]

    return "ok", "", []


def _score_candidate(tag: Tag) -> tuple[float, dict[str, float]]:
    tlen = _text_len(tag)
    if tlen <= 0:
        return -1e9, {"tlen": 0}

    plen = _paragraph_count(tag)
    hcnt = _heading_count(tag)
    ltxt = _link_text_len(tag)

    link_density = ltxt / max(1, tlen)
    sectiony = (
        1.0 if _SECTIONY_WORDS.search(tag.get_text(" ", strip=True)[:20000]) else 0.0
    )

    score = 0.0
    score += min(6000.0, float(tlen)) / 6000.0 * 6.0
    score += min(60.0, float(plen)) / 60.0 * 4.0
    score += min(30.0, float(hcnt)) / 30.0 * 2.0
    score -= min(1.0, float(link_density)) * 5.0
    score += sectiony * 1.5

    breakdown = {
        "tlen": float(tlen),
        "plen": float(plen),
        "hcnt": float(hcnt),
        "link_density": float(link_density),
        "sectiony": float(sectiony),
        "score": float(score),
    }
    return score, breakdown


def _normalize_heading_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _build_text_no_dupes(tag: Tag) -> str:
    """
    Build text without list duplication:
    - Keep <p> always (including those inside <li>)
    - Skip <li> if it contains <p> descendants
    """
    parts: list[str] = []
    for node in tag.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        if node.name == "li" and node.find("p") is not None:
            continue
        t = node.get_text(" ", strip=True)
        if not t:
            continue
        parts.append(t)
    return "\n".join(parts).strip()


def _split_body_and_references(best_tag: Tag) -> tuple[str, str, str, str, list[str]]:
    notes: list[str] = []

    ref_heading: Tag | None = None
    for h in best_tag.find_all(["h1", "h2", "h3", "h4"]):
        txt = _normalize_heading_text(h.get_text(" ", strip=True))
        if txt and _REF_HEADING_RX.match(txt):
            ref_heading = h
            break

    if not ref_heading:
        body_html = str(best_tag)
        body_text = _build_text_no_dupes(best_tag)
        return body_html, body_text, "", "", notes

    split_child: Tag | None = None
    for child in best_tag.find_all(recursive=False):
        if not isinstance(child, Tag):
            continue
        try:
            if child is ref_heading or child.find(lambda t: t is ref_heading):
                split_child = child
                break
        except Exception:
            continue

    if not split_child:
        # text-only split fallback
        all_text = _build_text_no_dupes(best_tag)
        lines = all_text.splitlines()
        out_body: list[str] = []
        out_refs: list[str] = []
        in_refs = False
        for ln in lines:
            if not in_refs and _REF_HEADING_RX.match(_normalize_heading_text(ln)):
                in_refs = True
            if in_refs:
                out_refs.append(ln)
            else:
                out_body.append(ln)
        notes.append("references_split_text_only")
        return (
            str(best_tag),
            "\n".join(out_body).strip(),
            "",
            "\n".join(out_refs).strip(),
            notes,
        )

    children = [c for c in best_tag.find_all(recursive=False) if isinstance(c, Tag)]
    try:
        idx = children.index(split_child)
    except ValueError:
        idx = 0

    body_children = children[:idx]
    refs_children = children[idx:]

    body_html = (
        '<div data-paperclip="article-body">'
        + "".join(str(c) for c in body_children)
        + "</div>"
    )
    refs_html = (
        '<div data-paperclip="references">'
        + "".join(str(c) for c in refs_children)
        + "</div>"
    )

    body_soup = BeautifulSoup(body_html, "html.parser")
    refs_soup = BeautifulSoup(refs_html, "html.parser")

    body_root = body_soup.find()
    refs_root = refs_soup.find()

    body_text = _build_text_no_dupes(body_root) if isinstance(body_root, Tag) else ""
    refs_text = _build_text_no_dupes(refs_root) if isinstance(refs_root, Tag) else ""

    notes.append("references_split_by_heading")
    notes.append(
        "references_heading:"
        + _normalize_heading_text(ref_heading.get_text(" ", strip=True))[:80]
    )

    return body_html, body_text, refs_html, refs_text, notes


def parse_generic(*, url: str, dom_html: str, head_meta: dict[str, Any]) -> ParseResult:
    if not dom_html.strip():
        return ParseResult(
            ok=False,
            parser="generic",
            capture_quality="suspicious",
            notes=["empty_dom_html"],
        )

    soup = BeautifulSoup(dom_html, "html.parser")
    quality, blocked_reason, wall_notes = _detect_wall(soup)

    candidates: list[tuple[str, Tag]] = []

    art = soup.find("article")
    if isinstance(art, Tag):
        candidates.append(("tag:article", art))

    main = soup.find("main")
    if isinstance(main, Tag):
        candidates.append(("tag:main", main))

    role_main = soup.find(attrs={"role": "main"})
    if isinstance(role_main, Tag):
        candidates.append(('attr:role="main"', role_main))

    for sel in [
        ("id:maincontent", soup.find(id="maincontent")),
        ("id:content", soup.find(id="content")),
        ("id:main", soup.find(id="main")),
    ]:
        if isinstance(sel[1], Tag):
            candidates.append((sel[0], sel[1]))

    best_block: tuple[str, Tag] | None = None
    best_block_len = 0
    for tag in soup.find_all(["div", "section"]):
        tl = _text_len(tag)
        if tl > best_block_len:
            best_block_len = tl
            best_block = ("fallback:largest_block", tag)
    if best_block is not None:
        candidates.append(best_block)

    seen = set()
    uniq: list[tuple[str, Tag]] = []
    for hint, t in candidates:
        if id(t) in seen:
            continue
        seen.add(id(t))
        uniq.append((hint, t))
    candidates = uniq

    best_hint = ""
    best_tag: Tag | None = None
    best_score = -1e9
    best_breakdown: dict[str, float] = {}

    for hint, tag in candidates:
        sub = BeautifulSoup(str(tag), "html.parser")
        root = sub.find()
        if not isinstance(root, Tag):
            continue

        _strip_noise(root)
        score, breakdown = _score_candidate(root)
        if score > best_score:
            best_score = score
            best_tag = root
            best_hint = hint
            best_breakdown = breakdown

    if not best_tag:
        return ParseResult(
            ok=False,
            parser="generic",
            capture_quality=quality,
            blocked_reason=blocked_reason,
            notes=["no_candidate_selected"] + wall_notes,
        )

    article_html, article_text, refs_html, refs_text, split_notes = (
        _split_body_and_references(best_tag)
    )

    if not (article_text or "").strip():
        article_text = best_tag.get_text("\n", strip=True)

    tlen = best_breakdown.get("tlen", 0.0)
    plen = best_breakdown.get("plen", 0.0)

    confidence = 0.0
    confidence += min(1.0, (best_score / 10.0))
    if tlen >= 2500:
        confidence += 0.25
    if plen >= 8:
        confidence += 0.25
    if quality == "blocked":
        confidence = min(confidence, 0.2)
    confidence = max(0.0, min(1.0, confidence))

    notes = wall_notes[:] + split_notes
    if best_hint.startswith("fallback"):
        notes.append("used_fallback_candidate")

    meta: dict[str, Any] = {}
    # NEW: sectionize the extracted article_text (body-only; references already split out)
    if (article_text or "").strip():
        meta.update(build_sections_meta(article_text))

    return ParseResult(
        ok=True,
        parser="generic",
        capture_quality=quality,
        blocked_reason=blocked_reason,
        confidence_fulltext=float(confidence),
        article_html=article_html,
        article_text=article_text,
        references_html=refs_html,
        references_text=refs_text,
        selected_hint=best_hint,
        score_breakdown=best_breakdown,
        notes=notes,
        meta=meta,
    )
