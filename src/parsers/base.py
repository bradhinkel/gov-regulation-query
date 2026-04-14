"""
src/parsers/base.py — Abstract base class for corpus parsers.

Every corpus (Sword Coast PDFs, eCFR XML, etc.) implements this interface.
The ingestion pipeline only depends on this ABC — adding a new corpus means
adding a new concrete parser, not changing any other code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class ChunkWithMetadata:
    """
    A single chunk of text with full citation metadata.

    Field names are corpus-agnostic so the same schema works for both
    Sword Coast and Government Regulation corpora.

    Government Regulation mapping:
        source_system      = "federal_regulations"
        corpus_type        = "cfr"
        source_id          = "cfr_title_7"
        location_reference = "7 CFR § 205.301 — Allowed and prohibited substances"
        title_number       = 7
        part_number        = "205"
        subpart            = "B"
        section_number     = "205.301"
        section_heading    = "Allowed and prohibited substances..."
        agency             = "Agricultural Marketing Service"
        cfr_reference      = "7 CFR § 205.301"
        effective_date     = "2024-01-01"
    """
    # Required for all corpora
    source_system: str
    corpus_type: str
    source_id: str
    location_reference: str
    chunk_text: str
    chunk_index: int = 0

    # CFR-specific fields (None for non-regulatory corpora)
    title_number: int | None = None
    part_number: str | None = None
    subpart: str | None = None
    section_number: str | None = None
    section_heading: str | None = None
    agency: str | None = None
    cfr_reference: str | None = None
    effective_date: str | None = None

    # Sword Coast compatibility fields (None for regulatory corpora)
    book_title: str | None = None
    chapter: str | None = None
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None

    # Extra metadata (not mapped to fixed columns)
    extra_metadata: dict = field(default_factory=dict)

    def citation_string(self) -> str:
        """Human-readable citation for display in the UI."""
        if self.cfr_reference:
            if self.section_heading:
                return f"{self.cfr_reference} — {self.section_heading}"
            return self.cfr_reference
        if self.book_title:
            parts = [self.book_title]
            if self.chapter:
                parts.append(self.chapter)
            if self.section:
                parts.append(f'"{self.section}"')
            if self.page_start:
                page = f"p. {self.page_start}"
                if self.page_end and self.page_end != self.page_start:
                    page += f"\u2013{self.page_end}"
                parts.append(page)
            return ", ".join(parts)
        return self.location_reference


class BaseParser(ABC):
    """
    Abstract parser — implement one per corpus type.

    Concrete implementations:
        src/parsers/xml_parser.py   — eCFR XML (federal regulations)
    """

    @abstractmethod
    def can_parse(self, source: object) -> bool:
        """Return True if this parser handles the given source."""
        ...

    @abstractmethod
    def parse(self, source: object) -> Iterator[ChunkWithMetadata]:
        """
        Yield ChunkWithMetadata objects for all chunks in the document.
        Implementations should be resumable (yield, don't batch).
        """
        ...

    @abstractmethod
    def source_id_for(self, source: object) -> str:
        """Return a stable slug identifier for the given source."""
        ...
