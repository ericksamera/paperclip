from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from bs4 import BeautifulSoup, Tag, NavigableString
import re, json
from urllib.parse import urlparse

# DOI pattern
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")

# ---------- Structured reference object ----------

@dataclass
class ReferenceObj:
    id: Optional[str]
    raw: str

    # Normalized fields (focus on the entry itself)
    title: Optional[str] = None
    authors: List[Dict[str, str]] = field(default_factory=list)  # [{family, given}]
    container_title: Optional[str] = None
    issued_year: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    url: Optional[str] = None

    doi: Optional[str] = None
    issn: Optional[str] = None
    isbn: Optional[str] = None

    # Keep enriched formats for lossless round-trips
    bibtex: Optional[str] = None
    apa: Optional[str] = None
    csl: Dict[str, Any] = field(default_factory=dict)

    # ---- Builders / mappers ----
    @classmethod
    def from_csl(cls, raw: str, csl: Dict[str, Any], id: Optional[str] = None) -> "ReferenceObj":
        if not isinstance(csl, dict):
            csl = {}
        title = csl.get("title")
        container = csl.get("container-title") or csl.get("container_title")
        if isinstance(container, list):
            container = container[0] if container else None
        issued_year = None
        issued = csl.get("issued") or csl.get("issued-date")
        # CSL issued could be {"date-parts":[[2024, 5, 1]]}
        if isinstance(issued, dict):
            parts = issued.get("date-parts") or issued.get("date_parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], (list, tuple)) and parts[0]:
                issued_year = str(parts[0][0])
        elif isinstance(issued, str):
            m = re.search(r"\b(19|20)\d{2}[a-z]?\b", issued)
            if m: issued_year = m.group(0)
        authors = []
        for a in csl.get("author", []) or []:
            fam = (a.get("family") or "").strip()
            giv = (a.get("given") or "").strip()
            if fam or giv:
                authors.append({"family": fam, "given": giv})
        doi = csl.get("DOI") or csl.get("doi")
        pages = csl.get("page") or csl.get("pages")
        return cls(
            id=id,
            raw=raw or title or "",
            title=title,
            authors=authors,
            container_title=container,
            issued_year=issued_year,
            volume=(csl.get("volume") or None),
            issue=(csl.get("issue") or None),
            pages=pages,
            publisher=(csl.get("publisher") or None),
            url=(csl.get("URL") or csl.get("url") or None),
            doi=doi,
            issn=(csl.get("ISSN") or csl.get("issn") or None),
            isbn=(csl.get("ISBN") or csl.get("isbn") or None),
            csl=csl
        )

    @classmethod
    def from_raw_heuristic(cls, raw: str, id: Optional[str] = None) -> "ReferenceObj":
        """
        Very lightweight heuristics for common APA-like strings:
        "Smith, J., Doe, A. (2021). Title here. Journal Name, 12(3), 45–67. https://doi.org/10...."
        """
        raw = (raw or "").strip()
        doi = None
        mdoi = DOI_RE.search(raw)
        if mdoi: doi = mdoi.group(0)

        # Year "(2021)" or "(2021a)"
        year = None
        my = re.search(r"\((?P<y>(19|20)\d{2}[a-z]?)\)", raw)
        if my: year = my.group("y")

        # Authors: match sequences of "Family, G." patterns before the year
        authors: List[Dict[str, str]] = []
        prefix = raw
        if my:
            prefix = raw[:my.start()]
        for nm in re.finditer(r"([A-Z][A-Za-z'´`\-]+),\s*([A-Z][.\-A-Za-z ]+)", prefix):
            fam = nm.group(1).strip()
            giv = nm.group(2).strip().rstrip(".")
            authors.append({"family": fam, "given": giv})

        # Title & journal
        title = None
        container = None
        # after year close paren, try: "). Title. Journal, 12(3), 45-67"
        tail = raw[my.end():] if my else raw
        # remove leading punctuation
        tail = re.sub(r"^[\s\.\-:;]+", " ", tail)
        mtj = re.search(r"^\s*(?P<title>[^.]+)\.\s+(?P<journal>[^.,]+)", tail)
        if mtj:
            title = mtj.group("title").strip()
            container = mtj.group("journal").strip()

        # Volume/issue/pages
        volume = issue = pages = None
        mvip = re.search(
            r"(?P<vol>\d+)\s*\(\s*(?P<iss>[^)]+)\s*\)\s*,\s*(?P<pgs>\d+[^\s,;)]*)", tail
        )
        if mvip:
            volume = mvip.group("vol")
            issue = mvip.group("iss")
            pages = mvip.group("pgs")
        else:
            mvp = re.search(r"(?P<vol>\d+)\s*,\s*(?P<pgs>\d+[^\s,;)]*)", tail)
            if mvp:
                volume = mvp.group("vol")
                pages = mvp.group("pgs")

        return cls(
            id=id, raw=raw, doi=doi, issued_year=year,
            title=title, container_title=container,
            authors=authors, volume=volume, issue=issue, pages=pages
        )

    def to_model_kwargs(self) -> Dict[str, Any]:
        return {
            "ref_id": self.id,
            "raw": self.raw,
            "csl": (self.csl or {}),
            "bibtex": self.bibtex,
            "apa": self.apa,

            "title": self.title or "",
            "authors": self.authors or [],
            "container_title": self.container_title or "",
            "issued_year": self.issued_year or "",
            "volume": self.volume or "",
            "issue": self.issue or "",
            "pages": self.pages or "",
            "publisher": self.publisher or "",
            "url": self.url,

            "doi": self.doi,
            "issn": self.issn or "",
            "isbn": self.isbn or "",
        }

# ---------- Base parser & utilities ----------

@dataclass
class ParseResult:
    meta_updates: Dict[str, Any]
    references: List[ReferenceObj]
    figures: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]

class BaseParser:
    DOMAINS: Tuple[str, ...] = tuple()
    NAME: str = "Generic"
    ABSTRACT_SELECTORS: Tuple[str, ...] = (
        "section.abstract",
        "section#abstract",
        "section#abstracts div.abstract",
        "div.abstract.author",
        "div#abstract",
        "div.abstract",
    )

    @classmethod
    def matches_domain(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host.endswith(d) for d in cls.DOMAINS) if cls.DOMAINS else False

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        return cls.matches_domain(url)

    @classmethod
    def parse(cls, url: str, soup: BeautifulSoup) -> ParseResult:
        refs = cls._harvest_references_generic(soup)
        meta_updates = cls._build_meta_updates(soup)
        return ParseResult(meta_updates=meta_updates, references=refs, figures=[], tables=[])

    # ---- shared helpers ----

    @staticmethod
    def _text(el: Optional[Tag]) -> str:
        return (el.get_text(" ", strip=True) if el else "").strip()

    @classmethod
    def _build_meta_updates(cls, soup: BeautifulSoup) -> Dict[str, Any]:
        meta_updates: Dict[str, Any] = {}
        abstract = cls._extract_abstract(soup)
        if abstract:
            meta_updates["abstract"] = abstract
        return meta_updates

    @classmethod
    def _extract_abstract(cls, soup: BeautifulSoup) -> str:
        seen: set[int] = set()
        for selector in cls.ABSTRACT_SELECTORS:
            for node in soup.select(selector):
                ident = id(node)
                if ident in seen:
                    continue
                seen.add(ident)
                if cls._should_skip_abstract_candidate(node):
                    continue
                text = cls._abstract_from_node(node)
                if text:
                    return text
        return ""

    @classmethod
    def _should_skip_abstract_candidate(cls, node: Tag) -> bool:
        return False

    @classmethod
    def _abstract_from_node(cls, node: Tag) -> str:
        text = node.get_text(" ", strip=True)
        if not text:
            return ""
        heading = cls._leading_heading(node)
        if heading:
            head_text = heading.get_text(" ", strip=True)
            if head_text:
                stripped = text.lstrip()
                if stripped.upper().startswith(head_text.upper()):
                    text = stripped[len(head_text):].strip()
        return " ".join(text.split())

    @staticmethod
    def _leading_heading(node: Tag) -> Optional[Tag]:
        for child in node.children:
            if isinstance(child, NavigableString):
                if child.strip():
                    break
                continue
            if child.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                return child
            if child.get_text(" ", strip=True):
                break
        return None

    @staticmethod
    def _find_reference_lists(soup: BeautifulSoup) -> List[Tag]:
        headings = soup.select("h1, h2, h3, h4, h5, h6")
        hits: List[Tag] = []
        for h in headings:
            if re.search(r"\b(references|bibliography|works cited)\b", h.get_text(" ", strip=True), re.I):
                sib = h.find_next_sibling()
                while sib and sib.name and sib.name.lower() not in ("ol", "ul", "div", "section"):
                    sib = sib.find_next_sibling()
                if sib:
                    lists = sib.select("ol, ul") if sib.name and sib.name.lower() in ("div", "section") else [sib]
                    hits.extend(lists)
        hits.extend(soup.select(
            "ol.references, ul.references, #references ol, #references ul, .references ol, .references ul, "
            "ol.ref-list, ul.ref-list, .ref-list, .article-references ol, .article-references ul"
        ))
        uniq, seen = [], set()
        for node in hits:
            if node and id(node) not in seen:
                uniq.append(node); seen.add(id(node))
        return uniq

    @classmethod
    def _harvest_references_generic(cls, soup: BeautifulSoup) -> List[ReferenceObj]:
        out: List[ReferenceObj] = []
        for lst in cls._find_reference_lists(soup):
            for li in lst.select(":scope > li"):
                raw = cls._text(li)
                if not raw:
                    continue
                # Prefer href DOI if a link exists
                href = ""
                a = li.select_one('a[href*="doi.org/10."]')
                if a and a.get("href"): href = a["href"]
                m = DOI_RE.search(href) or DOI_RE.search(raw)
                ref = ReferenceObj.from_raw_heuristic(raw, id=f"ref-{len(out)+1}")
                if m and not ref.doi:
                    ref.doi = m.group(0)
                out.append(ref)
        return out

    @staticmethod
    def _search_json_for_doi(obj: Any) -> Optional[str]:
        try:
            if isinstance(obj, dict):
                for _, v in obj.items():
                    found = BaseParser._search_json_for_doi(v)
                    if found: return found
            elif isinstance(obj, list):
                for it in obj:
                    found = BaseParser._search_json_for_doi(it)
                    if found: return found
            elif isinstance(obj, str):
                m = DOI_RE.search(obj)
                if m: return m.group(0)
        except Exception:
            pass
        return None

    @staticmethod
    def find_doi_in_meta(soup: BeautifulSoup) -> Optional[str]:
        for m in soup.find_all("meta"):
            name = (m.get("name") or m.get("property") or "").strip().lower()
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if name in (
                "citation_doi", "doi", "prism.doi",
                "dc.identifier", "dc.identifier.doi", "dc.identifier:doi", "og:doi",
            ) or ("doi" in name) or (name.startswith("dc.") and "identifier" in name):
                mm = DOI_RE.search(re.sub(r"(?i)^doi:\s*", "", content))
                if mm:
                    return mm.group(0)
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
            except Exception:
                continue
            found = BaseParser._search_json_for_doi(data)
            if found:
                return found
        a = soup.select_one('a[href*="doi.org/10."]')
        if a and a.get("href"):
            m = DOI_RE.search(a["href"])
            if m:
                return m.group(0)
        return None
