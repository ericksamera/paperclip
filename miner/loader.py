from dataclasses import dataclass
from pathlib import Path
import json

@dataclass
class Document:
    path: Path
    id: str
    title: str
    doi: str | None
    url: str | None
    year: str | None
    keywords: list[str]
    text: str
    references: list[dict]  # items may contain 'doi', 'csl', 'bibtex', 'raw', etc.

def _join_text(content: dict) -> str:
    # server_parsed.json -> { abstract: [ {body}... ], keywords: [..], body: [sections...] }
    parts = []
    for a in content.get("abstract", []) or []:
        parts.append(a.get("body", ""))
    for sec in content.get("body", []) or []:
        parts.append(sec.get("markdown", ""))
        for p in sec.get("paragraphs", []) or []:
            parts.append(p.get("markdown", ""))
    return "\n\n".join(p for p in parts if p)

def load_documents(inputs: list[str]) -> list[Document]:
    files: list[Path] = []
    for pattern in inputs:
        p = Path(pattern)
        if p.is_file():
            files.append(p)
        else:
            files.extend(Path().glob(pattern))
    docs: list[Document] = []
    for fp in sorted(set(files)):
        with open(fp, "r", encoding="utf-8") as f:
            obj = json.load(f)
        meta = obj.get("meta", {})
        content = obj.get("content", {})
        docs.append(Document(
            path=fp,
            id=obj.get("id") or meta.get("doi") or str(fp),
            title=meta.get("title") or (meta.get("source") or "Untitled"),
            doi=(meta.get("doi") or None),
            url=(obj.get("url") or meta.get("url") or None),
            year=(meta.get("issued_year") or None),
            keywords=list(content.get("keywords") or []),
            text=_join_text(content),
            references=list(obj.get("references") or []),
        ))
    return docs
