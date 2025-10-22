from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Reference(BaseModel):
    id: str | None = None
    raw: str | None = None
    title: str | None = None
    doi: str | None = None
    url: str | None = None
    issued_year: int | None = None
    authors: list[str] | None = None
    csl: dict[str, Any] = Field(default_factory=dict)
    container_title: str | None = None


class Section(BaseModel):
    title: str | None = None
    paragraphs: list[str] = Field(default_factory=list)


class Table(BaseModel):
    """Normalized representation of an HTML table."""

    id: str | None = None
    title: str | None = None  # e.g., "Table 1."
    caption: str | None = None  # human caption/description
    source_link: str | None = None  # "Open in new tab" href etc.
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)  # rectangular matrix
    records: list[dict[str, str]] = Field(
        default_factory=list
    )  # row dicts keyed by columns


class ServerParsed(BaseModel):
    id: str
    title: str | None = None
    url: str | None = None
    doi: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    abstract: list[Section] = Field(default_factory=list)
    body: list[Section] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)  # NEW
