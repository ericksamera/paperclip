from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Reference(BaseModel):
    id: Optional[str] = None
    raw: Optional[str] = None
    title: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    issued_year: Optional[int] = None
    authors: Optional[List[str]] = None
    csl: Dict[str, Any] = Field(default_factory=dict)
    container_title: Optional[str] = None

class Section(BaseModel):
    title: Optional[str] = None
    paragraphs: List[str] = Field(default_factory=list)

class ServerParsed(BaseModel):
    id: str
    title: Optional[str] = None
    url: Optional[str] = None
    doi: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    abstract: List[Section] = Field(default_factory=list)
    body: List[Section] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    references: List[Reference] = Field(default_factory=list)
