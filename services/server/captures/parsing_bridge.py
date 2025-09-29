# services/server/captures/parsing_bridge.py
from __future__ import annotations

import re
from typing import Any, Dict, List
from bs4 import BeautifulSoup, Tag

from captures.site_parsers import extract_sections_meta as _extract_site_sections_meta


def _t(x: Any) -> str:
    return (x or "").strip()


def _year_int(s: str | None) -> int | None:
    if not s:
        return None
    m = re.search(r"\b(19|20)\d{2}\b", s)
    return int(m.group(0)) if m else None


def _find_first(head: BeautifulSoup, names: List[str]) -> tuple[str | None, str | None]:
    """Return (content, matched_key) for the first meta[name|property] in names."""
    for n in names:
        tag = head.find("meta", attrs={"name": n}) or head.find("meta", attrs={"property": n})
        if tag and _t(tag.get("content")):
            return _t(tag.get("content")), n
    return None, None


def _keywords(head: BeautifulSoup) -> List[str]:
    vals: List[str] = []
    for tag in head.find_all("meta", attrs={"name": "citation_keywords"}):
        v = _t(tag.get("content"))
        if v:
            vals.append(v)
    kw_generic = head.find("meta", attrs={"name": "keywords"})
    if kw_generic and _t(kw_generic.get("content")):
        vals.append(_t(kw_generic.get("content")))

    parts: List[str] = []
    for v in vals:
        parts += [p.strip() for p in re.split(r"[;,/]|[\r\n]+", v) if p.strip()]

    out, seen = [], set()
    for k in parts:
        lk = k.lower()
        if lk not in seen:
            seen.add(lk)
            out.append(k)
    return out


def _split_authors_value(v: str) -> List[str]:
    chunks = re.split(r"\s*;\s*|\s+(?:and|&)\s+", v, flags=re.I)
    return [c.strip() for c in chunks if c.strip()]


def _authors(head: BeautifulSoup) -> List[str]:
    out: List[str] = []
    for tag in head.find_all("meta", attrs={"name": "citation_author"}):
        v = _t(tag.get("content"))
        if v:
            out.append(v)
    for alt in ("dc.creator", "dcterms.creator", "prism.author", "author", "citation_authors"):
        for tag in head.find_all("meta", attrs={"name": alt}):
            v = _t(tag.get("content"))
            if v:
                out.extend(_split_authors_value(v))
    seen, uniq = set(), []
    for a in out:
        la = a.lower()
        if la not in seen:
            seen.add(la)
            uniq.append(a)
    return uniq


# ----------------------- Fallbacks kept in-bridge (Wiley/PMC/generic) -----------------------

def _extract_pmc_abstract_and_keywords(dom_html: str) -> tuple[str | None, List[str]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")

    # ---- Abstract ----
    abstract = None

    # Wiley-first (most specific)
    for node in soup.select("section.article-section__abstract, div.abstract-group"):
        host = node.select_one(".article-section__content") or node
        paras = [p.get_text(" ", strip=True) for p in host.find_all("p")]
        paras = [p for p in paras if p]
        if paras:
            abstract = " ".join(paras)
            break

    # PMC / classic containers (fallbacks)
    if not abstract:
        abs_nodes = soup.select(
            "section.abstract, section#abstract, section[id^='abstract'], "
            "div.abstract, div#abstr, div#abstract"
        )
        for node in abs_nodes:
            paras = [p.get_text(" ", strip=True) for p in node.find_all("p")]
            paras = [p for p in paras if p]
            if paras:
                abstract = " ".join(paras)
                break

    # ---- Keywords ----
    kws: List[str] = []

    # Wiley keywords (various page templates)
    for kw_host in soup.find_all(
        lambda tag: tag.name in {"section", "div", "ul"}
        and any("keyword" in (c or "").lower() for c in (tag.get("class") or []))
    ):
        found = False
        for li in kw_host.find_all("li"):
            t = li.get_text(" ", strip=True)
            if t:
                kws.append(t)
                found = True
        if found:
            break
        txt = kw_host.get_text(" ", strip=True)
        if txt:
            txt = re.sub(r"^\s*Keywords?\s*:\s*", "", txt, flags=re.I)
            parts = [p.strip() for p in re.split(r"[;,/]|[\r\n]+", txt) if p.strip()]
            if parts:
                kws.extend(parts)
                break

    # PMC/generic hints
    if not kws:
        kw_nodes = soup.select("section.kwd-group, div.kwd-group, p:-soup-contains('Keywords:')")
        for node in kw_nodes:
            txt = node.get_text(" ", strip=True)
            txt = re.sub(r"^\s*Keywords?\s*:\s*", "", txt, flags=re.I)
            parts = [p.strip() for p in re.split(r"[;,/]|[\r\n]+", txt) if p.strip()]
            if parts:
                kws.extend(parts)
                break

    seen, out = set(), []
    for k in kws:
        lk = k.lower()
        if lk not in seen:
            seen.add(lk)
            out.append(k)
    return abstract, out


def _heading_text(h: Tag) -> str:
    txt = h.get_text(" ", strip=True)
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*[\.\)]?\s*", "", txt)


def _collect_direct_paragraphs(sec: Tag) -> List[str]:
    """
    Collect paragraphs that are DIRECT children of the section.
    Extended: also treat ScienceDirect-style paragraph DIVs as paragraphs.
    """
    out: List[str] = []
    for child in sec.children:
        if not isinstance(child, Tag):
            continue
        # classic <p>
        if child.name == "p":
            t = child.get_text(" ", strip=True)
            if t: out.append(t)
            continue
        # ScienceDirect paragraph divs: id="p0025" or class*="u-margin" or "*para*"
        if child.name == "div":
            did = (child.get("id") or "").lower()
            cls = " ".join((child.get("class") or [])).lower()
            if re.match(r"^p\d{3,}$", did) or "u-margin" in cls or "para" in cls or "paragraph" in cls:
                lis = [li.get_text(" ", strip=True) for li in child.find_all("li", recursive=True)]
                lis = [re.sub(r"\s+", " ", x).strip() for x in lis if x and len(x.strip()) > 1]
                if lis:
                    out.extend(lis)
                else:
                    t = child.get_text(" ", strip=True)
                    t = re.sub(r"\s+", " ", t).strip()
                    if t:
                        out.append(t)
    return out


def _parse_section_node(sec: Tag) -> Dict[str, Any]:
    h = sec.find(["h2", "h3", "h4"], recursive=False) or sec.find(["h2", "h3", "h4"])
    title = _heading_text(h) if h else ""
    paragraphs = _collect_direct_paragraphs(sec)

    children: List[Dict[str, Any]] = []
    for child_sec in sec.find_all("section", recursive=False):
        if "ref-list" in child_sec.get("class", []) or child_sec.get("role") in {"doc-footnote"}:
            continue
        children.append(_parse_section_node(child_sec))

    node: Dict[str, Any] = {"title": title, "paragraphs": paragraphs}
    if children:
        node["children"] = children
    return node


def _is_wiley_noncontent(sec: Tag) -> bool:
    classes = " ".join((sec.get("class") or [])).lower()
    sid = (sec.get("id") or "").lower()
    return (
        "article-section__abstract" in classes
        or "article-section__references" in classes
        or "references" in classes
        or "keyword" in classes
        or "kwd-group" in classes
        or re.search(r"(?:^|[-_])ref(?:erence|list)|bib|kwd|abstract", sid) is not None
    )


def _extract_sections_wiley(dom_html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: List[Dict[str, Any]] = []
    candidates = soup.find_all("section", id=re.compile(r"(?:^|-)sec-\d+|^sec", re.I))
    for sec in candidates:
        if _is_wiley_noncontent(sec):
            continue
        node = _parse_section_node(sec)
        if (node.get("title") or "").strip() or node.get("paragraphs") or node.get("children"):
            out.append(node)
    seen, uniq = set(), []
    for n in out:
        key = (n.get("title") or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            uniq.append(n)
    return uniq


def _inside_abstract_container(node: Tag) -> bool:
    cur = node.parent
    while isinstance(cur, Tag):
        classes = [c.lower() for c in (cur.get("class") or [])]
        cid = (cur.get("id") or "")
        if any("abstract" == c or "abstract" in c for c in classes) or re.match(r"^(abs|abstract)", cid, re.I):
            return True
        cur = cur.parent
    return False


def _extract_sections_pmc(dom_html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: List[Dict[str, Any]] = []

    for sec in soup.find_all("section", id=True):
        sid = sec.get("id", "")
        scls = sec.get("class", [])
        if not re.match(r"^sec", sid, re.I):
            continue
        if any("abstract" == c or "abstract" in (c or "").lower() for c in scls) \
           or re.match(r"^abstract", sid, re.I) \
           or _inside_abstract_container(sec):
            continue
        if "ref-list" in scls or re.match(r"^ref-list", sid, re.I):
            continue
        if "kwd-group" in scls:
            continue
        parent = sec.find_parent("section", id=re.compile(r"^sec", re.I))
        if parent:
            continue

        node = _parse_section_node(sec)
        if node.get("title") or node.get("paragraphs") or node.get("children"):
            out.append(node)

    return out


def _extract_sections_generic(dom_html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    root = soup.find("article") or soup.find("main") or soup.body or soup
    if not root:
        return []

    def level_of(tag: Tag) -> int:
        return {"h2": 2, "h3": 3, "h4": 4}.get(tag.name.lower(), 99)

    headings = [h for h in root.find_all(["h2", "h3", "h4"])]

    top: List[Dict[str, Any]] = []
    stack: List[tuple[int, Dict[str, Any]]] = []

    def paragraphs_between(h: Tag, next_h: Tag | None) -> List[str]:
        paras: List[str] = []
        sib = h.next_sibling
        while sib and sib is not next_h:
            if isinstance(sib, Tag):
                if sib.name in {"h2", "h3", "h4"}:
                    break
                # standard <p>
                for p in sib.find_all("p"):
                    t = p.get_text(" ", strip=True)
                    if t: paras.append(t)
                # ScienceDirect-style paragraph DIVs near headings
                for d in sib.find_all("div", recursive=False):
                    did = (d.get("id") or "").lower()
                    cls = " ".join((d.get("class") or [])).lower()
                    if re.match(r"^p\d{3,}$", did) or "u-margin" in cls or "para" in cls or "paragraph" in cls:
                        lis = [li.get_text(" ", strip=True) for li in d.find_all("li", recursive=True)]
                        lis = [re.sub(r"\s+", " ", x).strip() for x in lis if x and len(x.strip()) > 1]
                        if lis:
                            paras.extend(lis)
                        else:
                            t = d.get_text(" ", strip=True)
                            t = re.sub(r"\s+", " ", t).strip()
                            if t:
                                paras.append(t)
            sib = sib.next_sibling
        return paras

    for i, h in enumerate(headings):
        lvl = level_of(h)
        title = _heading_text(h)
        if not title:
            continue
        next_h = next((k for k in headings[i + 1:] if k), None)
        node: Dict[str, Any] = {"title": title, "paragraphs": paragraphs_between(h, next_h)}

        while stack and stack[-1][0] >= lvl:
            stack.pop()
        if stack:
            parent = stack[-1][1]
            parent.setdefault("children", []).append(node)
        else:
            top.append(node)
        stack.append((lvl, node))

    return top


def _extract_sections(dom_html: str) -> List[Dict[str, Any]]:
    sections = _extract_sections_wiley(dom_html)
    if not sections:
        sections = _extract_sections_pmc(dom_html)
    if not sections:
        sections = _extract_sections_generic(dom_html)

    def dedupe(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen, out = set(), []
        for n in nodes:
            t = (n.get("title") or "").strip().lower()
            key = (t, len(n.get("children", []) or []))
            if t and key in seen:
                continue
            seen.add(key)
            if n.get("children"):
                n["children"] = dedupe(n["children"])  # type: ignore[index]
            out.append(n)
        return out

    return dedupe(sections)


# ----------------------- Head/meta + robust_parse -----------------------

def _head_updates(dom_html: str, url: str | None = None) -> Dict[str, Any]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    head = soup.head or soup

    title_val, title_key = _find_first(head, ["citation_title", "dc.title", "dcterms.title", "prism.title"])
    if not title_val:
        title_val = _t(head.title.get_text(strip=True) if head and head.title else None)
        title_src = "html"
    else:
        if title_key and title_key.startswith("citation"):
            title_src = "citation"
        elif title_key and (title_key.startswith("dc.") or title_key.startswith("dcterms.")):
            title_src = "dc"
        elif title_key and title_key.startswith("prism."):
            title_src = "prism"
        else:
            title_src = "head"

    doi_val, _ = _find_first(head, ["citation_doi", "prism.doi", "dc.identifier", "dcterms.identifier"])
    year_val = _year_int(
        (_find_first(head, [
            "prism.publicationdate",
            "citation_publication_date",
            "citation_date",
            "dc.date",
            "dcterms.issued",
        ])[0])
    )
    journal_val, _ = _find_first(head, ["citation_journal_title", "prism.publicationname"])

    # 1) Ask site parser for abstract/keywords/sections
    site = {}
    try:
        site = _extract_site_sections_meta(url or "", dom_html or "") or {}
    except Exception:
        site = {}

    abs_text = site.get("abstract")
    kws_body = site.get("keywords") or []
    sections = site.get("sections") or []

    # 2) Fallbacks only if site parser had nothing
    if not abs_text or not sections:
        fb_abs, fb_kws = _extract_pmc_abstract_and_keywords(dom_html)
        abs_text = abs_text or fb_abs
        if not sections:
            sections = _extract_sections(dom_html)
        kws_body = (kws_body or []) or (fb_kws or [])

    out = {
        "title": title_val,
        "title_source": title_src,
        "doi": doi_val,
        "issued_year": year_val,
        "container_title": journal_val,
        "keywords": _keywords(head) + (kws_body or []),
        "authors": _authors(head),
        "sections": sections,
    }
    if abs_text:
        out["abstract"] = abs_text
    if url and not out.get("url"):
        out["url"] = url

    # De-dup keywords
    kw_seen, kw_out = set(), []
    for k in out["keywords"]:
        lk = (k or "").strip().lower()
        if lk and lk not in kw_seen:
            kw_seen.add(lk)
            kw_out.append(k)
    out["keywords"] = kw_out
    return out


def _paragraphs(content_html: str | None, dom_html: str | None) -> List[str]:
    """
    Build preview paragraphs from content_html (preferred) or DOM. If there are
    no <p> tags, treat ScienceDirect-style paragraph DIVs as paragraphs too.
    """
    html = content_html or dom_html or ""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("article") or soup.find("main") or soup
    paras: List[str] = [ _t(p.get_text(" ", strip=True)) for p in root.find_all("p") if _t(p.get_text(" ", strip=True)) ]

    if not paras:
        # SD-style paragraph DIVs as a fallback
        for d in root.find_all("div"):
            did = (d.get("id") or "").lower()
            cls = " ".join((d.get("class") or [])).lower()
            if re.match(r"^p\d{3,}$", did) or "u-margin" in cls or "para" in cls or "paragraph" in cls:
                t = d.get_text(" ", strip=True)
                t = re.sub(r"\s+", " ", t).strip()
                if t:
                    paras.append(t)
    return paras


def robust_parse(
    url: str | None,
    content_html: str,
    dom_html: str,
    meta: Dict[str, Any] | None = None,
    csl: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    head = _head_updates(dom_html or "", url)
    return {
        "meta_updates": head,
        "content_sections": {"abstract_or_body": _paragraphs(content_html, dom_html)},
    }
