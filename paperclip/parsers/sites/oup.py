from __future__ import annotations
from bs4 import BeautifulSoup
from ..base import BaseParser, ReferenceObj, DOI_RE

class OUPParser(BaseParser):
    NAME = "OUP"
    DOMAINS = ("academic.oup.com",)

    @classmethod
    def detect(cls, url: str, soup: BeautifulSoup) -> bool:
        if cls.matches_domain(url):
            return True

        canon = soup.find(
            "link",
            rel=lambda value: value
            and ("canonical" in (value if isinstance(value, str) else " ".join(value)).lower()),
        )
        if canon and "academic.oup.com" in (canon.get("href") or ""):
            return True

        publisher = soup.find("meta", attrs={"name": "dc.Publisher"}) or soup.find(
            "meta", attrs={"name": "DC.Publisher"}
        )
        if publisher and "Oxford" in (publisher.get("content") or ""):
            return True
        return False

    @classmethod
    def _harvest_references_generic(cls, soup: BeautifulSoup) -> list[ReferenceObj]:
        refs: list[ReferenceObj] = []
        for lst in soup.select(
            "#references ol, #References ol, .al-references ol, .ref-list ol, ol.references"
        ):
            for li in lst.select(":scope > li"):
                raw = cls._text(li)
                if not raw:
                    continue
                href = ""
                anchor = li.select_one('a[href*="doi.org/10."]')
                if anchor and anchor.get("href"):
                    href = anchor["href"]
                match = DOI_RE.search(href) or DOI_RE.search(raw)
                ref = ReferenceObj.from_raw_heuristic(raw, id=f"ref-{len(refs)+1}")
                if match and not ref.doi:
                    ref.doi = match.group(0)
                refs.append(ref)

        if refs:
            return refs

        return super()._harvest_references_generic(soup)
