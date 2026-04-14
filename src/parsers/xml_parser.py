"""
src/parsers/xml_parser.py — eCFR XML parser for federal regulations.

Fetches regulation XML from the eCFR API and chunks at § (section) boundaries.

eCFR XML hierarchy:
  DIV1 TYPE="TITLE"      — Title (e.g., Title 7: Agriculture)
  DIV2 TYPE="SUBTITLE"   — Subtitle (optional)
  DIV3 TYPE="CHAPTER"    — Chapter (optional)
  DIV4 TYPE="SUBCHAPTER" — Subchapter (optional)
  DIV5 TYPE="PART"       — Part (e.g., Part 205: National Organic Program)
  DIV6 TYPE="SUBPART"    — Subpart (optional, e.g., Subpart A: Definitions)
  DIV7 TYPE="SUBJGRP"    — Subject group (optional)
  DIV8 TYPE="SECTION"    — Section §  ← primary chunking boundary
  DIV9 TYPE="APPENDIX"   — Appendix (optional)

Each DIV8 contains:
  HEAD  — "§ 205.301   Allowed and prohibited substances."
  P     — paragraph text
  NOTE, CITA, AUTH, SOURCE — metadata elements (excluded from chunk text)

Usage:
    from src.parsers.xml_parser import ECFRXMLParser
    parser = ECFRXMLParser()
    for chunk in parser.parse(7):   # Title 7
        print(chunk.cfr_reference, len(chunk.chunk_text))
"""

import os
import re
import time
from datetime import date
from typing import Iterator

import httpx
from lxml import etree

from src.parsers.base import BaseParser, ChunkWithMetadata

ECFR_API_BASE = os.getenv("ECFR_API_BASE", "https://www.ecfr.gov/api/versioner/v1")

# Chunking constants — start with Sword Coast Phase 2 winner (1200 chars)
# Override via env vars for eval sweeps
TARGET_CHUNK_CHARS = int(os.getenv("TARGET_CHUNK_CHARS", "1200"))
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", "150"))
MIN_CHUNK_CHARS = int(os.getenv("MIN_CHUNK_CHARS", "100"))

# Elements whose text content should NOT be included in chunk_text
_SKIP_TAGS = {"AUTH", "SOURCE", "CITA", "FTREF", "EDNOTE", "EXTRACT", "GPOTABLE"}

# Regex to extract section number from HEAD text like "§ 205.301   Heading."
_SECTION_RE = re.compile(r"§\s*([\d.]+(?:-\d+)?)")


def _get_latest_date(title_number: int) -> str:
    """Return the most recent available date for a title from the eCFR versions API."""
    url = f"{ECFR_API_BASE}/versions/title-{title_number}.json"
    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # content_versions is a list sorted by date desc
        versions = data.get("content_versions", [])
        if versions:
            return versions[0].get("date", date.today().isoformat())
    except Exception:
        pass
    return date.today().isoformat()


def _fetch_title_xml(title_number: int, as_of_date: str | None = None) -> bytes:
    """Fetch the full title XML from the eCFR API."""
    if as_of_date is None:
        as_of_date = _get_latest_date(title_number)
    url = f"{ECFR_API_BASE}/full/{as_of_date}/title-{title_number}.xml"
    resp = httpx.get(url, timeout=120, follow_redirects=True)
    resp.raise_for_status()
    return resp.content, as_of_date


def _element_text(el) -> str:
    """Recursively extract all text from an element, skipping metadata sub-elements."""
    if el.tag in _SKIP_TAGS:
        return ""
    parts = []
    if el.text:
        parts.append(el.text.strip())
    for child in el:
        child_text = _element_text(child)
        if child_text:
            parts.append(child_text)
        if child.tail:
            parts.append(child.tail.strip())
    return " ".join(p for p in parts if p)


def _split_text(text: str, target: int = TARGET_CHUNK_CHARS,
                overlap: int = CHUNK_OVERLAP_CHARS,
                min_chars: int = MIN_CHUNK_CHARS) -> list[str]:
    """Split long text into overlapping chunks at sentence boundaries."""
    if len(text) <= target:
        return [text] if len(text) >= min_chars else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + target
        if end >= len(text):
            chunk = text[start:]
            if len(chunk) >= min_chars:
                chunks.append(chunk)
            break
        cut = text.rfind(". ", start, end)
        if cut == -1 or cut < start + target // 2:
            cut = text.rfind(" ", start, end)
        if cut == -1:
            cut = end
        else:
            cut += 1
        chunk = text[start:cut].strip()
        if len(chunk) >= min_chars:
            chunks.append(chunk)
        start = max(cut - overlap, start + 1)
    return chunks


class ECFRXMLParser(BaseParser):
    """Parses eCFR XML into regulation chunks, one § section per chunk."""

    SOURCE_SYSTEM = "federal_regulations"

    def __init__(self, source_system: str | None = None):
        self.source_system = source_system or os.getenv("SOURCE_SYSTEM", self.SOURCE_SYSTEM)

    def can_parse(self, source: object) -> bool:
        """Accept integer title numbers or paths to local XML files."""
        return isinstance(source, (int, str))

    def source_id_for(self, source: object) -> str:
        if isinstance(source, int):
            return f"cfr_title_{source}"
        return f"cfr_local_{source}"

    def parse(self, source: object) -> Iterator[ChunkWithMetadata]:
        """
        Yield ChunkWithMetadata for each § section in the title.

        Args:
            source: integer CFR title number (e.g., 7) or path to local XML file
        """
        if isinstance(source, int):
            xml_bytes, as_of_date = _fetch_title_xml(source)
            title_number = source
        else:
            with open(source, "rb") as f:
                xml_bytes = f.read()
            as_of_date = date.today().isoformat()
            title_number = None

        root = etree.fromstring(xml_bytes)
        yield from self._parse_root(root, title_number, as_of_date)

    def _parse_root(
        self, root, title_number: int | None, effective_date: str
    ) -> Iterator[ChunkWithMetadata]:
        source_id = f"cfr_title_{title_number}" if title_number else "cfr_local"
        chunk_index = 0

        # Walk the entire tree looking for SECTION elements (DIV8)
        # Context elements: TITLE → SUBTITLE → CHAPTER → SUBCHAPTER → PART → SUBPART
        # We collect context as we descend

        def walk(el, ctx: dict) -> Iterator[ChunkWithMetadata]:
            nonlocal chunk_index
            el_type = el.get("TYPE", "")
            head_el = el.find("HEAD")
            head_text = (head_el.text or "").strip() if head_el is not None else ""

            # Update context based on element type
            new_ctx = dict(ctx)
            if el_type == "TITLE":
                new_ctx["title_head"] = head_text
            elif el_type == "SUBTITLE":
                new_ctx["subtitle"] = head_text
            elif el_type == "CHAPTER":
                new_ctx["chapter"] = head_text
            elif el_type == "SUBCHAPTER":
                new_ctx["subchapter"] = head_text
            elif el_type == "PART":
                new_ctx["part"] = head_text
                new_ctx["part_number"] = el.get("N", "")
                new_ctx["agency"] = _infer_agency(head_text, ctx.get("chapter", ""))
            elif el_type == "SUBPART":
                new_ctx["subpart"] = head_text
                new_ctx["subpart_id"] = el.get("N", "")
            elif el_type == "SECTION":
                # This is a § section — primary chunk unit
                section_n = el.get("N", "")
                section_head = head_text  # e.g. "§ 205.301   Allowed and..."

                # Extract the § number from the HEAD text
                m = _SECTION_RE.search(section_head)
                section_number = m.group(1) if m else section_n

                # Extract heading (text after the § number)
                section_heading = re.sub(r"^§\s*[\d.\-]+\s*", "", section_head).strip().rstrip(".")

                # Build full text from P, NOTE, etc. (skip metadata elements)
                text_parts = []
                for child in el:
                    if child.tag == "HEAD":
                        continue
                    if child.tag in _SKIP_TAGS:
                        continue
                    t = _element_text(child)
                    if t:
                        text_parts.append(t)
                full_text = " ".join(text_parts).strip()

                if not full_text or len(full_text) < MIN_CHUNK_CHARS:
                    return

                cfr_ref = f"{title_number} CFR \u00a7 {section_number}" if title_number else f"\u00a7 {section_number}"
                location = cfr_ref
                if section_heading:
                    location += f" \u2014 {section_heading}"

                # Build context prefix for chunks
                context_prefix = f"[{cfr_ref}]\n"
                if section_heading:
                    context_prefix += f"{section_heading}\n\n"

                # Chunk the section text (most sections fit in one chunk)
                chunks = _split_text(full_text)
                if not chunks:
                    chunks = [full_text[:TARGET_CHUNK_CHARS]]

                for sub_chunk in chunks:
                    yield ChunkWithMetadata(
                        source_system=self.source_system,
                        corpus_type="cfr",
                        source_id=source_id,
                        location_reference=location,
                        title_number=title_number,
                        part_number=new_ctx.get("part_number"),
                        subpart=new_ctx.get("subpart_id"),
                        section_number=section_number,
                        section_heading=section_heading or None,
                        agency=new_ctx.get("agency"),
                        cfr_reference=cfr_ref,
                        effective_date=effective_date,
                        chunk_text=context_prefix + sub_chunk,
                        chunk_index=chunk_index,
                    )
                    chunk_index += 1
                return  # Don't recurse into section children

            # Recurse into children
            for child in el:
                yield from walk(child, new_ctx)

        yield from walk(root, {})


def _infer_agency(part_head: str, chapter_head: str) -> str | None:
    """Best-effort: extract agency name from chapter/part heading."""
    for text in (chapter_head, part_head):
        m = re.search(r"(?:Chapter\s+\w+—|CHAPTER\s+\w+—)\s*(.+)", text, re.I)
        if m:
            return m.group(1).strip()
    return None
