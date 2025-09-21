from __future__ import annotations
from dataclasses import dataclass, field
import json
import re
from typing import Any, Callable, Optional, Sequence, TypedDict
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

# DOI pattern
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")

# ---------- Structured reference object ----------

class AbstractSection(TypedDict):
    title: Optional[str]
    body: str


@dataclass
class ReferenceObj:
    id: Optional[str]
    raw: str

    # Normalized fields (focus on the entry itself)
    title: Optional[str] = None
    authors: list[dict[str, str]] = field(default_factory=list)  # [{family, given}]
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
    csl: dict[str, Any] = field(default_factory=dict)

    # ---- Builders / mappers ----
    @classmethod
    def from_csl(cls, raw: str, csl: dict[str, Any], id: Optional[str] = None) -> "ReferenceObj":
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
            match = re.search(r"\b(19|20)\d{2}[a-z]?\b", issued)
            if match:
                issued_year = match.group(0)
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

    def merge_csl(self, csl: dict[str, Any]) -> None:
        """Backfill missing fields using CSL metadata."""

        if not isinstance(csl, dict):
            return

        enriched = ReferenceObj.from_csl(self.raw, csl, id=self.id)

        if not self.title and enriched.title:
            self.title = enriched.title
        if not self.authors and enriched.authors:
            self.authors = enriched.authors
        if not self.container_title and enriched.container_title:
            self.container_title = enriched.container_title
        if not self.issued_year and enriched.issued_year:
            self.issued_year = enriched.issued_year
        if not self.volume and enriched.volume:
            self.volume = enriched.volume
        if not self.issue and enriched.issue:
            self.issue = enriched.issue
        if not self.pages and enriched.pages:
            self.pages = enriched.pages
        if not self.publisher and enriched.publisher:
            self.publisher = enriched.publisher
        if not self.url and enriched.url:
            self.url = enriched.url
        if not self.doi and enriched.doi:
            self.doi = enriched.doi
        if not self.issn and enriched.issn:
            self.issn = enriched.issn
        if not self.isbn and enriched.isbn:
            self.isbn = enriched.isbn

        if enriched.csl:
            self.csl = enriched.csl

    @classmethod
    def from_raw_heuristic(cls, raw: str, id: Optional[str] = None) -> "ReferenceObj":
        """
        Very lightweight heuristics for common APA-like strings:
        "Smith, J., Doe, A. (2021). Title here. Journal Name, 12(3), 45–67. https://doi.org/10...."
        """
        raw = (raw or "").strip()
        doi = None
        mdoi = DOI_RE.search(raw)
        if mdoi:
            doi = mdoi.group(0)

        # Year "(2021)" or "(2021a)"
        year = None
        my = re.search(r"\(\s*(?P<y>(?:19|20)\d{2}[a-z]?)\s*\)", raw)
        if my:
            year = my.group("y").strip()

        # Authors: match sequences of "Family, G." patterns before the year
        authors: list[dict[str, str]] = []
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
            r"(?P<vol>\d+)\s*\(\s*(?P<iss>[^)]+)\s*\)\s*,\s*(?P<pgs>\d+(?:\s*[\u2013\u2014-]\s*\d+)?)",
            tail,
        )
        if mvip:
            volume = mvip.group("vol")
            issue = mvip.group("iss")
            pages = mvip.group("pgs")
        else:
            mvp = re.search(
                r"(?P<vol>\d+)\s*,\s*(?P<pgs>\d+(?:\s*[\u2013\u2014-]\s*\d+)?)",
                tail,
            )
            if mvp:
                volume = mvp.group("vol")
                pages = mvp.group("pgs")

        return cls(
            id=id, raw=raw, doi=doi, issued_year=year,
            title=title, container_title=container,
            authors=authors, volume=volume, issue=issue, pages=pages
        )

    def to_model_kwargs(self) -> dict[str, Any]:
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
    meta_updates: dict[str, Any]
    content_sections: dict[str, Any]
    references: list[ReferenceObj]
    figures: list[dict[str, Any]]
    tables: list[dict[str, Any]]

class BaseParser:
    DOMAINS: tuple[str, ...] = tuple()
    NAME: str = "Generic"
    ABSTRACT_SELECTORS: tuple[str, ...] = (
        "section.abstract",
        "section#abstract",
        "section#abstracts div.abstract",
        "div.abstract.author",
        "div#abstract",
        "div.abstract",
    )

    KEYWORD_CONTAINER_SELECTORS: tuple[str, ...] = (
        "section.Keywords",
        "div.Keywords",
        "section.keywords",
        "div.keywords",
        "section.keywords-section",
        "div.keywords-section",
        "section.keyword-section",
        "div.keyword-section",
        "section.keyword-list",
        "div.keyword-list",
        "section.kwd-group",
        "div.kwd-group",
        "section[data-type='keywords']",
        "div[data-type='keywords']",
        "section[itemprop='keywords']",
        "div[itemprop='keywords']",
        "ul.keywords",
        "ol.keywords",
    )

    KEYWORD_NODE_SELECTORS: tuple[str, ...] = (
        ":scope div.keyword",
        ":scope span.keyword",
        ":scope li.keyword",
        ":scope a.keyword",
        ":scope span.kwd",
        ":scope li.kwd",
        ":scope a.kwd",
    )

    KEYWORD_FALLBACK_SELECTORS: tuple[str, ...] = (
        "div.keyword",
        "span.keyword",
        "li.keyword",
        "a.keyword",
        "span.kwd",
        "li.kwd",
        "a.kwd",
    )

    KEYWORD_META_NAMES: tuple[str, ...] = (
        "citation_keywords",
        "keywords",
        "keyword",
        "dc.subject",
        "dc.subject.keywords",
        "dc.keywords",
        "dc.subject:keywords",
        "dcterms.subject",
        "article:tag",
        "og:article:tag",
        "prism.keyword",
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
        content_sections = cls._build_content_sections(soup)
        doi = cls.find_doi_in_meta(soup)
        if doi and not meta_updates.get("doi"):
            meta_updates["doi"] = doi
        return ParseResult(
            meta_updates=meta_updates,
            content_sections=content_sections,
            references=refs,
            figures=[],
            tables=[],
        )

    # ---- shared helpers ----

    @staticmethod
    def _text(el: Optional[Tag]) -> str:
        return (el.get_text(" ", strip=True) if el else "").strip()

    @classmethod
    def _build_meta_updates(cls, soup: BeautifulSoup) -> dict[str, Any]:
        return {}

    @classmethod
    def _build_content_sections(cls, soup: BeautifulSoup) -> dict[str, Any]:
        content: dict[str, Any] = {}
        abstract_sections = cls._extract_abstract(soup)
        if abstract_sections:
            content["abstract"] = abstract_sections
        keywords = cls._extract_keywords(soup)
        if keywords:
            content["keywords"] = keywords
        return content

    @classmethod
    def _extract_abstract(cls, soup: BeautifulSoup) -> list[AbstractSection]:
        seen: set[int] = set()
        for selector in cls.ABSTRACT_SELECTORS:
            for node in soup.select(selector):
                ident = id(node)
                if ident in seen:
                    continue
                seen.add(ident)
                if cls._should_skip_abstract_candidate(node):
                    continue
                sections = cls._abstract_from_node(node)
                if sections:
                    return sections
        return []

    @classmethod
    def _should_skip_abstract_candidate(cls, node: Tag) -> bool:
        return False

    @classmethod
    def _abstract_from_node(cls, node: Tag) -> list[AbstractSection]:
        structured = cls._abstract_structured_sections(node)
        if structured:
            return structured

        text = node.get_text(" ", strip=True)
        if not text:
            return []
        heading = cls._leading_heading(node)
        if heading:
            head_text = heading.get_text(" ", strip=True)
            if head_text:
                stripped = text.lstrip()
                if stripped.upper().startswith(head_text.upper()):
                    text = stripped[len(head_text):].strip()
        collapsed = " ".join(text.split())
        return [{"title": None, "body": collapsed}] if collapsed else []

    @classmethod
    def _abstract_structured_sections(cls, node: Tag) -> list[AbstractSection]:
        sections: list[AbstractSection] = []
        pending_text: list[str] = []
        found_structured = False

        def flush_pending() -> None:
            if not pending_text:
                return
            text = " ".join(" ".join(pending_text).split())
            pending_text.clear()
            if text:
                sections.append({"title": None, "body": text})

        for child in node.children:
            if isinstance(child, NavigableString):
                snippet = child.strip()
                if snippet:
                    pending_text.append(snippet)
                continue
            if not isinstance(child, Tag):
                continue

            if cls._is_structured_abstract_section(child):
                found_structured = True
                flush_pending()
                built = cls._build_structured_section(child)
                if built:
                    sections.append(built)
                continue

            nested = cls._abstract_structured_sections(child)
            if nested:
                found_structured = True
                flush_pending()
                sections.extend(nested)
            else:
                text = child.get_text(" ", strip=True)
                if text:
                    pending_text.append(text)

        flush_pending()

        if not found_structured:
            return []
        return [section for section in sections if section.get("body")]

    @classmethod
    def _build_structured_section(cls, node: Tag) -> Optional[AbstractSection]:
        title = cls._abstract_section_title(node)
        body = cls._abstract_section_body(node, title)
        if not body:
            return None
        return {"title": title, "body": body}

    @staticmethod
    def _is_structured_abstract_section(node: Tag) -> bool:
        classes = [c.lower() for c in (node.get("class") or []) if isinstance(c, str)]
        if not classes:
            return False
        for cls_name in classes:
            if cls_name in {"sec", "section"}:
                return True
            if cls_name.endswith("sec") or cls_name.endswith("section"):
                return True
            if "abstract" in cls_name and "section" in cls_name:
                return True
        return False

    @classmethod
    def _abstract_section_title(cls, node: Tag) -> Optional[str]:
        for child in node.find_all(True, recursive=False):
            classes = [c.lower() for c in (child.get("class") or []) if isinstance(c, str)]
            if classes and any("title" == c or c.endswith("title") or "title" in c for c in classes):
                title_text = child.get_text(" ", strip=True)
                if title_text:
                    return " ".join(title_text.split())
        heading = node.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading:
            title_text = heading.get_text(" ", strip=True)
            if title_text:
                return " ".join(title_text.split())
        return None

    @classmethod
    def _abstract_section_body(cls, node: Tag, title: Optional[str]) -> str:
        text = node.get_text(" ", strip=True)
        if not text:
            return ""
        if title:
            stripped = text.lstrip()
            normalized_title = " ".join(title.split())
            if stripped.upper().startswith(normalized_title.upper()):
                text = stripped[len(normalized_title):].strip()
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

    @classmethod
    def _extract_keywords(cls, soup: BeautifulSoup) -> list[str]:
        keywords: list[str] = []
        seen: set[str] = set()

        def record(text: str) -> None:
            normalized = text.lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                keywords.append(text)

        containers: list[Tag] = []
        for selector in cls.KEYWORD_CONTAINER_SELECTORS:
            for node in soup.select(selector):
                if isinstance(node, Tag):
                    containers.append(node)

        containers = cls._dedupe_nodes(containers)

        if not containers:
            fallback_nodes: list[Tag] = []
            for selector in cls.KEYWORD_FALLBACK_SELECTORS:
                for node in soup.select(selector):
                    if isinstance(node, Tag):
                        fallback_nodes.append(node)
            fallback_nodes = cls._dedupe_nodes(fallback_nodes)
            if fallback_nodes:
                containers = [node.parent or node for node in fallback_nodes if isinstance(node, Tag)]
                containers = cls._dedupe_nodes(containers)
                # If we still have no containers, treat the fallback nodes as individual keywords.
                if not containers:
                    for node in fallback_nodes:
                        text = cls._keyword_text(node)
                        if text:
                            record(text)

        for container in containers:
            cls._collect_keywords_from_container(container, record)

        for text in cls._keywords_from_meta(soup):
            if text:
                record(text)

        return keywords

    @classmethod
    def _collect_keywords_from_container(cls, container: Tag, record: Callable[[str], None]) -> None:
        if cls._node_is_keyword_item(container):
            text = cls._keyword_text(container)
            if text:
                record(text)

        for selector in cls.KEYWORD_NODE_SELECTORS:
            for node in container.select(selector):
                if not isinstance(node, Tag):
                    continue
                text = cls._keyword_text(node)
                if text:
                    record(text)

        if cls._node_is_keyword_container(container):
            for node in container.select(":scope li, :scope span, :scope a, :scope p"):
                if not isinstance(node, Tag):
                    continue
                if node is container:
                    continue
                if cls._node_is_keyword_container(node) or cls._node_is_keyword_item(node):
                    continue
                text = cls._keyword_text(node)
                if text:
                    record(text)

    @classmethod
    def _keywords_from_meta(cls, soup: BeautifulSoup) -> list[str]:
        collected: list[str] = []
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or meta.get("property") or meta.get("itemprop") or "").strip().lower()
            content = (meta.get("content") or "").strip()
            if not content:
                continue
            if cls._meta_name_is_keyword(name):
                for token in cls._split_keywords(content):
                    if token:
                        collected.append(token)
        return collected

    @classmethod
    def _meta_name_is_keyword(cls, name: str) -> bool:
        if not name:
            return False
        if name in cls.KEYWORD_META_NAMES:
            return True
        if "keyword" in name:
            return True
        if name.startswith("dc.") and "subject" in name:
            return True
        return False

    @staticmethod
    def _split_keywords(content: str) -> list[str]:
        parts = re.split(r"[,;\n\r\t]|\s*\|\s*", content)
        return [part.strip() for part in parts if part.strip()]

    @classmethod
    def _node_is_keyword_container(cls, node: Tag) -> bool:
        for value in cls._keyword_marker_values(node):
            low = value.lower()
            if "keywords" in low:
                return True
            if "keyword-list" in low or "keywordlist" in low:
                return True
            if low.endswith("-group") and "kwd" in low:
                return True
        return False

    @classmethod
    def _node_is_keyword_item(cls, node: Tag) -> bool:
        for value in cls._keyword_marker_values(node):
            low = value.lower()
            if low == "keyword" or low.endswith("-keyword") or low.endswith("_keyword"):
                return True
            if low == "kwd" or low.endswith("-kwd"):
                return True
            if low in {"article:tag", "article-tag"}:
                return True
        return False

    @staticmethod
    def _keyword_marker_values(node: Tag) -> list[str]:
        values: list[str] = []
        for attr in ("class", "role", "data-type", "data_type", "itemprop", "rel"):
            attr_value = node.get(attr)
            if not attr_value:
                continue
            if isinstance(attr_value, (list, tuple)):
                values.extend(str(v) for v in attr_value if isinstance(v, (str, bytes)))
            else:
                values.append(str(attr_value))
        return values

    @staticmethod
    def _keyword_text(node: Tag) -> str:
        text = node.get_text(" ", strip=True)
        return " ".join(text.split())

    @staticmethod
    def _dedupe_nodes(nodes: Sequence[Tag]) -> list[Tag]:
        uniq: list[Tag] = []
        seen_ids: set[int] = set()
        for node in nodes:
            ident = id(node)
            if ident in seen_ids:
                continue
            seen_ids.add(ident)
            uniq.append(node)
        return uniq

    @staticmethod
    def _find_reference_lists(soup: BeautifulSoup) -> list[Tag]:
        headings = soup.select("h1, h2, h3, h4, h5, h6")
        hits: list[Tag] = []
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
        uniq: list[Tag] = []
        seen: set[int] = set()
        for node in hits:
            if node and id(node) not in seen:
                uniq.append(node)
                seen.add(id(node))
        return uniq

    @classmethod
    def _harvest_references_generic(cls, soup: BeautifulSoup) -> list[ReferenceObj]:
        out: list[ReferenceObj] = []
        for lst in cls._find_reference_lists(soup):
            for li in lst.select(":scope > li"):
                raw = cls._text(li)
                if not raw:
                    continue
                # Prefer href DOI if a link exists
                href = ""
                anchor = li.select_one('a[href*="doi.org/10."]')
                if anchor and anchor.get("href"):
                    href = anchor["href"]
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
                    if found:
                        return found
            elif isinstance(obj, list):
                for it in obj:
                    found = BaseParser._search_json_for_doi(it)
                    if found:
                        return found
            elif isinstance(obj, str):
                m = DOI_RE.search(obj)
                if m:
                    return m.group(0)
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
