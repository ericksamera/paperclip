# services/server/captures/parsing_bridge.py
from __future__ import annotations

import re
from typing import Any, Dict, List
from bs4 import BeautifulSoup, Tag


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


# ----------------------- PMC abstract + keywords -----------------------

def _extract_pmc_abstract_and_keywords(dom_html: str) -> tuple[str | None, List[str]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")

    # Abstract
    abstract = None
    abs_nodes = soup.select(
        "section.abstract, section#abstract, section[id^=abstract], div.abstract, div#abstr, div#abstract"
    )
    for node in abs_nodes:
        paras = [p.get_text(" ", strip=True) for p in node.find_all("p")]
        paras = [p for p in paras if p]
        if paras:
            abstract = " ".join(paras)
            break  # first good one wins

    # Keywords: kwd-group or a <p> containing “Keywords:”
    kws: List[str] = []
    kw_nodes = soup.select("section.kwd-group, div.kwd-group, p:-soup-contains('Keywords:')")
    for node in kw_nodes:
        txt = node.get_text(" ", strip=True)
        txt = re.sub(r"^\s*Keywords?\s*:\s*", "", txt, flags=re.I)
        for tok in re.split(r"[;,/]|[\r\n]+", txt):
            tok = tok.strip()
            if tok and tok.lower() not in {x.lower() for x in kws}:
                kws.append(tok)
        if kws:
            break

    return abstract, kws


# ----------------------- Section extraction (nested) -----------------------

def _heading_text(h: Tag) -> str:
    txt = h.get_text(" ", strip=True)
    # Strip outline numbers like "2.", "2.4", "1)" etc.
    txt = re.sub(r"^\s*\d+(?:\.\d+)*\s*[\.\)]?\s*", "", txt)
    return txt


def _collect_direct_paragraphs(sec: Tag) -> List[str]:
    """Only paragraphs that are DIRECT children (not nested sections)."""
    paras: List[str] = []
    for child in sec.children:
        if isinstance(child, Tag) and child.name == "p":
            t = child.get_text(" ", strip=True)
            if t:
                paras.append(t)
    return paras


def _parse_section_node(sec: Tag) -> Dict[str, Any]:
    """
    Build a nested section dict from a PMC <section> node:
      { title, paragraphs[], children[] }
    """
    h = sec.find(["h2", "h3", "h4"], recursive=False) or sec.find(["h2", "h3", "h4"])
    title = _heading_text(h) if h else ""
    paragraphs = _collect_direct_paragraphs(sec)

    # children = immediate nested <section> nodes
    children: List[Dict[str, Any]] = []
    for child_sec in sec.find_all("section", recursive=False):
        # skip non-content subnodes (e.g., tables inside section)
        if "ref-list" in child_sec.get("class", []) or child_sec.get("role") in {"doc-footnote"}:
            continue
        children.append(_parse_section_node(child_sec))

    node: Dict[str, Any] = {"title": title, "paragraphs": paragraphs}
    if children:
        node["children"] = children
    return node


def _inside_abstract_container(node: Tag) -> bool:
    """
    True if node is under an abstract wrapper (e.g., <section class="abstract" id="Abs1">…).
    PMC uses class="abstract" and sometimes ids like Abs1/abstract.
    """
    cur = node.parent
    while isinstance(cur, Tag):
        classes = [c.lower() for c in (cur.get("class") or [])]
        cid = (cur.get("id") or "")
        if "abstract" in classes or re.match(r"^(abs|abstract)", cid, re.I):
            return True
        cur = cur.parent
    return False


def _extract_sections_pmc(dom_html: str) -> List[Dict[str, Any]]:
    """
    Parse PMC sections such as:
      <section id="Sec1"><h2>Background</h2> ... <section><h3>…</h3> ...</section> …</section>

    Notes:
    * PMC uses both `id="secX"` and `id="SecX"`; match **case-insensitively**.
    * Skip known non-content blocks (abstract, references, keywords).
    * Also skip *structured-abstract* parts (sec1.. inside the Abstract container).
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    out: List[Dict[str, Any]] = []

    # Candidate top-level sections: id starting with "sec" (case-insensitively)
    for sec in soup.find_all("section", id=True):
        sid = sec.get("id", "")
        scls = sec.get("class", [])
        if not re.match(r"^sec", sid, re.I):
            continue
        # ignore anything that is the abstract itself OR lives under it
        if "abstract" in scls or re.match(r"^abstract", sid, re.I) or _inside_abstract_container(sec):
            continue
        if "ref-list" in scls or re.match(r"^ref-list", sid, re.I):
            continue
        if "kwd-group" in scls:
            continue
        # only top-most (no parent with id^=sec)
        parent = sec.find_parent("section", id=re.compile(r"^sec", re.I))
        if parent:
            continue

        node = _parse_section_node(sec)
        if node.get("title") or node.get("paragraphs") or node.get("children"):
            out.append(node)

    return out


def _extract_sections_generic(dom_html: str) -> List[Dict[str, Any]]:
    """
    Fallback: build a tree using heading levels (h2<h3<h4) under <article>/<main> (or body).
    Nodes: { title, paragraphs[], children[]? }
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")
    root = soup.find("article") or soup.find("main") or soup.body or soup
    if not root:
        return []

    def level_of(tag: Tag) -> int:
        return {"h2": 2, "h3": 3, "h4": 4}.get(tag.name.lower(), 99)

    headings = [h for h in root.find_all(["h2", "h3", "h4"])]

    top: List[Dict[str, Any]] = []
    stack: List[tuple[int, Dict[str, Any]]] = []  # (level, node)

    def paragraphs_between(h: Tag, next_h: Tag | None) -> List[str]:
        paras: List[str] = []
        sib = h.next_sibling
        while sib and sib is not next_h:
            if isinstance(sib, Tag):
                if sib.name in {"h2", "h3", "h4"}:
                    break
                for p in sib.find_all("p"):
                    t = p.get_text(" ", strip=True)
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
    # Prefer PMC-specific, otherwise generic fallback
    sections = _extract_sections_pmc(dom_html)
    if not sections:
        sections = _extract_sections_generic(dom_html)

    # Deduplicate by title at a given level (simple guard)
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

def _head_updates(dom_html: str) -> Dict[str, Any]:
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

    abs_text, kws_body = _extract_pmc_abstract_and_keywords(dom_html)
    sections = _extract_sections(dom_html)

    out = {
        "title": title_val,
        "title_source": title_src,
        "doi": doi_val,
        "issued_year": year_val,
        "container_title": journal_val,
        "keywords": _keywords(head) + (kws_body or []),
        "authors": _authors(head),
        "sections": sections,  # nested sections tree (no structured-abstract duplicates)
    }
    if abs_text:
        out["abstract"] = abs_text

    # de-dup keywords
    kw_seen, kw_out = set(), []
    for k in out["keywords"]:
        lk = k.lower()
        if lk not in kw_seen:
            kw_seen.add(lk)
            kw_out.append(k)
    out["keywords"] = kw_out
    return out


def _paragraphs(content_html: str | None, dom_html: str | None) -> List[str]:
    html = content_html or dom_html or ""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("article") or soup.find("main") or soup
    paras: List[str] = []
    for p in root.find_all("p"):
        t = _t(p.get_text(" ", strip=True))
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
    """
    Returns:
      {
        "meta_updates": {title, title_source, doi, issued_year, container_title, keywords, authors,
                         abstract?, sections[nested], url?},
        "content_sections": {"abstract_or_body": ["para1", "para2", ...]}
      }
    """
    head = _head_updates(dom_html or "")
    if url and not head.get("url"):
        head["url"] = url

    return {
        "meta_updates": head,
        "content_sections": {"abstract_or_body": _paragraphs(content_html, dom_html)},
    }
