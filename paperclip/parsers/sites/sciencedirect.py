from __future__ import annotations
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from ..base import BaseParser, ReferenceObj, DOI_RE

class ScienceDirectParser(BaseParser):
    NAME = "ScienceDirect"
    DOMAINS = ("sciencedirect.com", "elsevier.com")

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        if cls.matches_domain(url):
            return True

        canon = soup.find(
            "link",
            rel=lambda value: value
            and ("canonical" in (value if isinstance(value, str) else " ".join(value)).lower()),
        )
        if canon and "sciencedirect.com" in (canon.get("href") or ""):
            return True

        publisher = soup.find("meta", attrs={"name": "citation_publisher"})
        if publisher and "Elsevier" in (publisher.get("content") or ""):
            return True

        site = soup.find("meta", attrs={"property": "og:site_name"})
        if site and "ScienceDirect" in (site.get("content") or ""):
            return True
        return False

    @classmethod
    def _harvest_references_generic(cls, soup: BeautifulSoup) -> list[ReferenceObj]:
        refs: list[ReferenceObj] = []
        selectors = [
            "section#references ol",
            "div#references ol",
            "ol.reference",
            "ol.bibliography",
            "div[class*='Reference'] ol",
        ]
        for sel in selectors:
            for lst in soup.select(sel):
                for li in lst.select(":scope > li"):
                    raw = cls._text(li)
                    if not raw:
                        continue
                    ref_id = f"ref-{len(refs) + 1}"
                    ref = cls._build_reference_from_node(li, ref_id, raw)
                    href = cls._extract_reference_href(li)
                    match = DOI_RE.search(href or "") or DOI_RE.search(ref.raw)
                    if match and not ref.doi:
                        ref.doi = match.group(0)
                    refs.append(ref)

        if refs:
            return refs

        return super()._harvest_references_generic(soup)

    @classmethod
    def _build_reference_from_node(cls, node: Tag, ref_id: str, fallback_raw: str) -> ReferenceObj:
        authors_text = cls._text(node.select_one(".authors"))
        title_text = cls._text(node.select_one(".title"))
        host_nodes = [cls._text(host) for host in node.select(".host")]
        host_nodes = [text for text in host_nodes if text]
        comment_nodes = [cls._text(comment) for comment in node.select(".comment")]
        comment_nodes = [text for text in comment_nodes if text]

        combined_text = " ".join(host_nodes + comment_nodes)
        year_match = re.search(r"\b(19|20)\d{2}[a-z]?\b", combined_text)
        year = year_match.group(0) if year_match else None

        raw_parts: list[str] = []
        if authors_text:
            raw_parts.append(authors_text.rstrip(". "))
        if year:
            raw_parts.append(f"({year})")
        if title_text:
            raw_parts.append(title_text.rstrip(". "))
        if host_nodes:
            raw_parts.append(", ".join(host_nodes))
        if comment_nodes:
            raw_parts.append(" ".join(comment_nodes))

        raw_candidate = ". ".join(part for part in raw_parts if part)
        raw = raw_candidate or fallback_raw

        ref = ReferenceObj.from_raw_heuristic(raw, id=ref_id)
        if not ref.raw:
            ref.raw = raw

        if title_text:
            ref.title = title_text
        if year:
            ref.issued_year = year

        authors = cls._parse_authors(authors_text)
        if authors:
            ref.authors = authors

        primary_host = host_nodes[0] if host_nodes else ""
        container, volume, issue, pages = cls._parse_host_metadata(primary_host, year)
        if container:
            ref.container_title = container
        if volume and not ref.volume:
            ref.volume = volume
        if issue and not ref.issue:
            ref.issue = issue
        if pages and not ref.pages:
            ref.pages = pages

        url = cls._select_preferred_url(node)
        if url and not ref.url:
            ref.url = url

        return ref

    @staticmethod
    def _extract_reference_href(node: Tag) -> Optional[str]:
        anchor = node.select_one('a[href*="doi.org/10."]')
        if anchor and anchor.get("href"):
            return anchor["href"]
        return None

    @classmethod
    def _parse_authors(cls, text: str) -> list[dict[str, str]]:
        if not text:
            return []
        cleaned = re.sub(r"\band\b", ",", text, flags=re.I)
        parts = [part.strip() for part in cleaned.split(",") if part.strip()]
        authors: list[dict[str, str]] = []
        buffer = ""
        for part in parts:
            candidate = f"{buffer} {part}".strip() if buffer else part
            if cls._is_name_suffix(part):
                buffer = candidate
                continue
            parsed = cls._parse_author_segment(candidate)
            if parsed:
                authors.append(parsed)
            buffer = ""
        if buffer:
            parsed = cls._parse_author_segment(buffer)
            if parsed:
                authors.append(parsed)
        return authors

    @staticmethod
    def _is_name_suffix(segment: str) -> bool:
        suffix = segment.strip().lower().rstrip(".")
        return suffix in {"jr", "sr", "ii", "iii", "iv"}

    @staticmethod
    def _parse_author_segment(segment: str) -> Optional[dict[str, str]]:
        seg = re.sub(r"\s+", " ", segment.strip().strip(",;"))
        if not seg:
            return None

        if "," in seg:
            family, given = [part.strip(" .") for part in seg.split(",", 1)]
            if not family and not given:
                return None
            return {"family": family, "given": given}

        tokens = seg.split()
        suffix = None
        if tokens and ScienceDirectParser._is_name_suffix(tokens[-1]):
            suffix = tokens.pop()
        if not tokens:
            return None

        if len(tokens) == 1:
            family = tokens[0]
            given_tokens: list[str] = []
        else:
            first = tokens[0]
            last = tokens[-1]
            if "." in first and "." not in last:
                family = last
                given_tokens = tokens[:-1]
            elif "." in last and "." not in first:
                family = first
                given_tokens = tokens[1:]
            else:
                family = last
                given_tokens = tokens[:-1]

        if suffix:
            given_tokens = given_tokens + [suffix]

        family = family.strip(" .,")
        given = " ".join(given_tokens).strip(" .,")
        if not family and not given:
            return None
        return {"family": family, "given": given}

    @staticmethod
    def _parse_host_metadata(text: str, year: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        if not text:
            return None, None, None, None
        clean = re.sub(r"\s+", " ", text).strip()
        if not clean:
            return None, None, None, None

        container = clean
        rest = ""
        if "," in clean:
            container = clean.split(",", 1)[0].strip()
            rest = clean[len(container):].lstrip(", ")

        if year:
            rest = re.sub(rf"\(\s*{re.escape(year)}\s*\)", "", rest)

        search_scope = rest or clean

        pages = None
        match_pages = re.search(r"pp?\.?\s*([0-9]+(?:[-–][0-9]+)?)", search_scope, flags=re.I)
        if match_pages:
            pages = match_pages.group(1)

        volume = None
        for match_volume in re.finditer(r"\b(\d{1,4})\b", search_scope):
            candidate = match_volume.group(1)
            if year and (candidate == year or candidate in year):
                continue
            if len(candidate) == 4 and candidate.startswith(("19", "20")):
                continue
            volume = candidate
            break

        issue = None
        for match_issue in re.finditer(r"\(([^)]+)\)", search_scope):
            content = match_issue.group(1).strip()
            if not content:
                continue
            if year and re.search(re.escape(year[:4]), content):
                continue
            if pages and content.replace(" ", "") in pages.replace(" ", ""):
                continue
            if content.isdigit() and len(content) == 4 and content.startswith(("19", "20")):
                continue
            issue = content
            break

        return (
            container or None,
            volume,
            issue,
            pages,
        )

    @staticmethod
    def _select_preferred_url(node: Tag) -> Optional[str]:
        candidates: list[str] = []
        for anchor in node.select("a[href]"):
            href = anchor.get("href")
            if not href or href.startswith("#"):
                continue
            if href.lower().startswith("javascript"):
                continue
            candidates.append(href)

        for href in candidates:
            if "doi.org" in href.lower():
                return href
        for href in candidates:
            if href.startswith("http"):
                return href
        return candidates[0] if candidates else None

    @classmethod
    def _should_skip_abstract_candidate(cls, node: Tag) -> bool:
        if super()._should_skip_abstract_candidate(node):
            return True
        classes = {
            value.lower()
            for value in (node.get("class") or [])
            if isinstance(value, str)
        }
        skip_markers = {
            "graphical",
            "graphicalabstract",
            "graphical-abstract",
            "highlights",
        }
        if classes & skip_markers:
            return True
        heading = cls._leading_heading(node)
        if heading:
            heading_text = heading.get_text(" ", strip=True).lower()
            if heading_text.startswith("graphical abstract"):
                return True
            if heading_text.startswith("graphical summary"):
                return True
