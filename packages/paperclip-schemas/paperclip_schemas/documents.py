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
