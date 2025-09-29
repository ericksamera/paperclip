# services/server/captures/site_parsers/sciencedirect.py
from __future__ import annotations
from typing import Dict, List
import re
from bs4 import BeautifulSoup, Tag

from . import register, register_meta
from .base import DOI_RE, YEAR_RE, collapse_spaces, norm, tokenize_authors_csv, authors_initials_first_to_surname_initials

# ------------------ References (existing) ------------------

def parse_sciencedirect(url: str, dom_html: str) -> List[Dict[str, object]]:
    soup = BeautifulSoup(dom_html or "", "html.parser")
    refs: List[Dict[str, object]] = []
    for ref in soup.select("span.reference, div.reference"):
        item: Dict[str, object] = {"raw": collapse_spaces(ref.get_text(" ", strip=True))}
        a_node = ref.select_one(".authors")
        if a_node:
            auths_raw = tokenize_authors_csv(collapse_spaces(a_node.get_text(" ", strip=True)))
            item["authors"] = authors_initials_first_to_surname_initials(auths_raw)
        t_node = ref.select_one(".title")
        if t_node:
            item["title"] = collapse_spaces(t_node.get_text(" ", strip=True))
        h_node = ref.select_one(".host")
        if h_node:
            host = collapse_spaces(h_node.get_text(" ", strip=True))
            m = re.search(r"^(?P<journal>.+?),\s*(?P<vol>\d+)\s*\((?P<year>\d{4})\)", host)
            if m:
                item["container_title"] = collapse_spaces(m.group("journal"))
                item["volume"] = m.group("vol")
                item["issued_year"] = m.group("year")
            mp = re.search(r"pp\.\s*([\d\-–]+)", host) or re.search(r":\s*([\d\-–]+)", host)
            if mp: item["pages"] = mp.group(1)
        doi = ""
        for a in ref.select(".ReferenceLinks a[href]"):
            m = DOI_RE.search(a.get("href", ""))
            if m: doi = m.group(0); break
        item["doi"] = doi
        if not item.get("issued_year"):
            my = YEAR_RE.search(item["raw"])  # type: ignore[index]
            if my: item["issued_year"] = my.group(0)
        for k in ("doi","title","container_title","volume","issued_year","pages"):
            item[k] = norm(item.get(k))  # type: ignore[index]
        refs.append(item)
    return refs

register(r"(?:^|\.)sciencedirect\.com$", parse_sciencedirect, where="host", name="ScienceDirect")

# ------------------ Meta / Sections (new) ------------------

def _heading_text(h: Tag | None) -> str:
    if not h:
        return ""
    txt = re.sub(r"\s+", " ", h.get_text(" ", strip=True)).strip()
    # Strip outline numbers like "1.", "2.4", "1)"
    return re.sub(r"^\s*\d+(?:\.\d+)*\s*[\.\)]?\s*", "", txt)

def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen, out = set(), []
    for k in items:
        lk = k.lower().strip()
        if lk and lk not in seen:
            seen.add(lk)
            out.append(k.strip())
    return out

_PARA_DIV_ID = re.compile(r"^p\d{3,}$", re.I)

def _looks_like_para_div(el: Tag) -> bool:
    """ScienceDirect uses <div class="u-margin-s-bottom" id="p0025">…</div> for paragraphs."""
    if not isinstance(el, Tag) or el.name != "div":
        return False
    did = (el.get("id") or "").lower()
    cls = " ".join((el.get("class") or [])).lower()
    return bool(_PARA_DIV_ID.match(did) or "u-margin" in cls or "para" in cls or "paragraph" in cls)

def _collect_sd_paragraphs(sec: Tag) -> List[str]:
    """Collect visible text blocks directly under a <section> (SD paragraphs are divs)."""
    out: List[str] = []

    # 1) Normal <p> children (few SD pages have them)
    for p in sec.find_all("p", recursive=False):
        t = p.get_text(" ", strip=True)
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            out.append(t)

    # 2) SD paragraph DIVs: id="p0025" / class~="u-margin-s-bottom"
    for d in sec.find_all("div", recursive=False):
        if not _looks_like_para_div(d): 
            continue
        # SD sometimes nests lists or spans inside these divs; keep list items too
        lis = [li.get_text(" ", strip=True) for li in d.find_all("li", recursive=True)]
        lis = [re.sub(r"\s+", " ", x).strip() for x in lis if x and len(x.strip()) > 1]
        if lis:
            out.extend(lis)
            continue

        t = d.get_text(" ", strip=True)
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            out.append(t)

    # 3) Direct UL/OL children at section root
    for ul in sec.find_all(["ul", "ol"], recursive=False):
        for li in ul.find_all("li", recursive=True):
            t = li.get_text(" ", strip=True)
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                out.append(t)

    return out

_NONCONTENT_RX = re.compile(
    r"\b(references?|acknowledg|conflict of interest|ethics|funding|data availability|author contributions?)\b",
    re.I,
)

def _parse_sd_section(sec: Tag) -> Dict[str, object]:
    """Recursively parse an SD <section> into {title, paragraphs, children?}."""
    h = sec.find(["h2", "h3", "h4"], recursive=False) or sec.find(["h2", "h3", "h4"])
    title = _heading_text(h) if h else ""
    # Skip obvious non-content buckets (we still keep "Abstract"/"Keywords" if present)
    if title and _NONCONTENT_RX.search(title):
        return {}

    paragraphs = _collect_sd_paragraphs(sec)

    children: List[Dict[str, object]] = []
    for child_sec in sec.find_all("section", recursive=False):
        node = _parse_sd_section(child_sec)
        if node and (node.get("title") or node.get("paragraphs") or node.get("children")):
            children.append(node)

    node: Dict[str, object] = {"title": title, "paragraphs": paragraphs}
    if children:
        node["children"] = children
    return node

def _extract_sd_sections(soup: BeautifulSoup) -> List[Dict[str, object]]:
    """
    ScienceDirect marks content with <section id="s0005">, <section id="s0010"> ...
    We take top-level 's####' sections (no parent 's####') and recurse.
    """
    sections: List[Dict[str, object]] = []
    all_secs = soup.select("section[id^='s']")
    # Keep only top-level s#### (no parent s####)
    top_secs = [s for s in all_secs if not s.find_parent("section", id=re.compile(r"^s\d{3,}$", re.I))]
    for sec in top_secs:
        node = _parse_sd_section(sec)
        if node and (node.get("title") or node.get("paragraphs") or node.get("children")):
            sections.append(node)

    # De-dup by title (case-insensitive), keep order
    seen, uniq = set(), []
    for n in sections:
        t = (n.get("title") or "").strip().lower()
        if t and t not in seen:
            seen.add(t)
            uniq.append(n)
    return uniq

def extract_sciencedirect_meta(_url: str, dom_html: str) -> Dict[str, object]:
    """
    Extract Abstract + Keywords + Sections from ScienceDirect article pages.

    Abstract:
      <div class="abstract author" id="ab0005">
        <h2>Abstract</h2>
        <div id="as0005"><div class="u-margin-s-bottom"> ... </div></div>
      </div>
    Body sections:
      <section id="s0005"><h2>…</h2><div id="p0025" class="u-margin-s-bottom"><span>…</span></div>…</section>
    """
    soup = BeautifulSoup(dom_html or "", "html.parser")

    # --- Abstract ---
    abstract = None
    for host in soup.select("div.abstract, section.abstract, div[class*='Abstract']"):
        title = _heading_text(host.find(["h2", "h3", "h4"]))
        if not re.search(r"\babstract\b", title, re.I):
            # Accept containers like id="ab0005"
            cid = (host.get("id") or "").lower()
            if not re.match(r"^ab\d+", cid):
                continue
        # Content often lives under an inner div whose id starts with 'as'
        inner = host.find(id=re.compile(r"^as\d+", re.I)) or host
        paras = [p.get_text(" ", strip=True) for p in inner.find_all("p")]
        if not paras:
            # Many SD abstracts use div.u-margin-s-bottom blocks
            paras = [d.get_text(" ", strip=True) for d in inner.find_all("div", class_=re.compile(r"u-margin", re.I))]
        paras = [re.sub(r"\s+", " ", t).strip() for t in paras if t.strip()]
        if paras:
            abstract = " ".join(paras)
            break

    # --- Keywords ---
    kws: List[str] = []
    for kw_wrap in soup.select("div[class*='keyword'], section[class*='keyword']"):
        items = []
        items += [a.get_text(" ", strip=True) for a in kw_wrap.select("a.keyword, a[class*='keyword']")]
        items += [span.get_text(" ", strip=True) for span in kw_wrap.select("span.keyword, span[class*='keyword']")]
        items += [li.get_text(" ", strip=True) for li in kw_wrap.select("li")]
        items = [re.sub(r"^\s*Keywords?\s*:\s*", "", t, flags=re.I) for t in items]
        items = [re.sub(r"\s+", " ", t).strip() for t in items if t and len(t.strip()) > 1]
        if items:
            kws.extend(items)
            break  # take first good block
    kws = _dedupe_keep_order(kws)

    # --- Sections ---
    sections = _extract_sd_sections(soup)

    return {"abstract": abstract, "keywords": kws, "sections": sections}

# Register meta extractor
register_meta(r"(?:^|\.)sciencedirect\.com$", extract_sciencedirect_meta, where="host", name="ScienceDirect meta")
