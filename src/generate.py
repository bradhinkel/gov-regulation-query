"""
src/generate.py — Three-output generation for federal regulations.

Produces three outputs from retrieved regulation chunks:
  1. plain_english   — clear, jargon-free summary for general audience
  2. legal_language  — authoritative synthesis in legal/regulatory register,
                       with verbatim quotes from source text (public domain)
  3. citations       — structured CFR citation list (Title/Part/Section)

Two strategies (controlled by LLM_CALL_STRATEGY env var):
  "single"     — one LLM call returning all outputs as structured JSON (faster)
  "sequential" — two separate calls: plain English first, then legal language
                 with verbatim quotes woven in (higher fidelity)

ENABLE_VERBATIM_QUOTES=true for this project — federal regulations are public domain.
"""

import json
import os
import time
from dataclasses import dataclass

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

GENERATION_MODEL = os.getenv("GENERATION_MODEL", "claude-haiku-4-5-20251001")
ENABLE_VERBATIM_QUOTES = os.getenv("ENABLE_VERBATIM_QUOTES", "true").lower() == "true"
LLM_CALL_STRATEGY = os.getenv("LLM_CALL_STRATEGY", "sequential")

_client = anthropic.Anthropic()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class CFRCitation(BaseModel):
    cfr_reference: str              # "7 CFR § 205.301"
    title_number: int | None = None
    part_number: str | None = None
    section_number: str | None = None
    section_heading: str | None = None
    agency: str | None = None
    source_id: str

    def citation_string(self) -> str:
        if self.section_heading:
            return f"{self.cfr_reference} \u2014 {self.section_heading}"
        return self.cfr_reference


class QueryResponse(BaseModel):
    plain_english: str
    legal_language: str
    citations: list[CFRCitation]
    strategy_used: str
    not_found: bool = False


@dataclass
class GenerationResult:
    response: QueryResponse
    input_tokens: int
    output_tokens: int
    latency_ms: float


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_VERBATIM_NOTE = (
    "\n\nWhen the regulatory text directly supports a claim, quote it verbatim "
    'and mark it with the CFR citation: "quoted text" (7 CFR § X.Y).'
    if ENABLE_VERBATIM_QUOTES
    else ""
)

_PLAIN_ENGLISH_SYSTEM = (
    "You are a federal regulatory expert explaining regulations to the general public. "
    "Answer clearly and concisely in plain, jargon-free English. "
    "Be accurate — do not add information not present in the provided context. "
    "If the context does not contain enough information to answer, respond with exactly: "
    '{"not_found": true}'
)

_LEGAL_SYSTEM = (
    "You are a legal analyst drafting an authoritative regulatory summary. "
    "Write in formal legal/regulatory register. "
    "Synthesize the retrieved regulatory text into a coherent answer. "
    "Federal regulations are public domain — include verbatim quotations where they "
    "precisely support the answer, marking each with its CFR citation in parentheses. "
    "Base your answer ONLY on the provided context. Do not invent or infer regulatory requirements."
    + _VERBATIM_NOTE
)

_SINGLE_CALL_SYSTEM = f"""\
You are a federal regulatory expert. Answer the question using ONLY the provided regulatory context.
Produce a JSON response with exactly this structure:
{{
  "plain_english": "Clear, jargon-free answer for a general audience. Write NOT_FOUND if context is insufficient.",
  "legal_language": "Formal regulatory-register answer with verbatim quotes from the source text (federal regulations are public domain). Write NOT_FOUND if context is insufficient.",
  "not_found": false
}}

Rules:
- Do not add requirements or interpretations not present in the context.
- If context is insufficient, set not_found=true and both text fields to "".
- plain_english: accessible, direct, no legal jargon.
- legal_language: formal register, cite specific CFR sections, include verbatim quotes where relevant.{_VERBATIM_NOTE}

Respond with ONLY the JSON object. No markdown fences."""


def _build_context_block(chunks) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Source {i}: {chunk.citation_string()}]\n{chunk.chunk_text}")
    return "\n\n---\n\n".join(parts)


def _citations_from_chunks(chunks) -> list[CFRCitation]:
    """Build citation list from chunk metadata — no LLM inference needed."""
    seen = set()
    citations = []
    for chunk in chunks:
        key = chunk.cfr_reference or chunk.source_id
        if key not in seen:
            seen.add(key)
            citations.append(CFRCitation(
                cfr_reference=chunk.cfr_reference or chunk.source_id,
                title_number=chunk.title_number,
                part_number=chunk.part_number,
                section_number=chunk.section_number,
                section_heading=chunk.section_heading,
                agency=getattr(chunk, "agency", None),
                source_id=chunk.source_id,
            ))
    return citations


# ---------------------------------------------------------------------------
# Single-call strategy
# ---------------------------------------------------------------------------

def _generate_single(query: str, chunks) -> GenerationResult:
    context = _build_context_block(chunks)
    prompt = f"Regulatory Context:\n{context}\n\nQuestion: {query}"

    t0 = time.time()
    response = _client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=1536,
        system=_SINGLE_CALL_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = (time.time() - t0) * 1000

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"plain_english": raw, "legal_language": raw, "not_found": False}

    not_found = data.get("not_found", False) or data.get("plain_english", "") in ("NOT_FOUND", "")

    qr = QueryResponse(
        plain_english=data.get("plain_english", ""),
        legal_language=data.get("legal_language", ""),
        citations=_citations_from_chunks(chunks),
        strategy_used="single",
        not_found=not_found,
    )
    return GenerationResult(
        response=qr,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# Sequential-call strategy
# ---------------------------------------------------------------------------

def _generate_sequential(query: str, chunks) -> GenerationResult:
    context = _build_context_block(chunks)
    user_msg = f"Regulatory Context:\n{context}\n\nQuestion: {query}"

    total_input = 0
    total_output = 0
    t0 = time.time()

    # Call 1: Plain English
    r1 = _client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=768,
        system=_PLAIN_ENGLISH_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    plain_text = r1.content[0].text.strip()
    total_input += r1.usage.input_tokens
    total_output += r1.usage.output_tokens

    not_found = '{"not_found": true}' in plain_text or plain_text == '{"not_found": true}'

    if not_found:
        qr = QueryResponse(
            plain_english="",
            legal_language="",
            citations=[],
            strategy_used="sequential",
            not_found=True,
        )
        return GenerationResult(qr, total_input, total_output, (time.time() - t0) * 1000)

    # Call 2: Legal Language with verbatim quotes
    legal_user = (
        f"Regulatory Context:\n{context}\n\n"
        f"Plain English summary:\n{plain_text}\n\n"
        "Now write the authoritative legal/regulatory language answer. "
        "Use formal regulatory register. Include verbatim quotes from the source text "
        "where they precisely support the answer (federal regulations are public domain). "
        "Cite each quote with its CFR reference. Base your answer only on the context above."
    )
    r2 = _client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=1024,
        system=_LEGAL_SYSTEM,
        messages=[{"role": "user", "content": legal_user}],
    )
    legal_text = r2.content[0].text.strip()
    total_input += r2.usage.input_tokens
    total_output += r2.usage.output_tokens

    qr = QueryResponse(
        plain_english=plain_text,
        legal_language=legal_text,
        citations=_citations_from_chunks(chunks),
        strategy_used="sequential",
        not_found=False,
    )
    return GenerationResult(qr, total_input, total_output, (time.time() - t0) * 1000)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate(query: str, chunks, strategy: str | None = None) -> GenerationResult:
    """
    Generate a three-output response from retrieved regulation chunks.

    Args:
        query:    The user's natural language question
        chunks:   List of RetrievedChunk objects from src/query.py
        strategy: Override LLM_CALL_STRATEGY ("single" | "sequential")

    Returns:
        GenerationResult with QueryResponse and token/latency stats
    """
    if not chunks:
        qr = QueryResponse(
            plain_english="",
            legal_language="",
            citations=[],
            strategy_used=strategy or LLM_CALL_STRATEGY,
            not_found=True,
        )
        return GenerationResult(qr, 0, 0, 0.0)

    strat = strategy or LLM_CALL_STRATEGY
    if strat == "sequential":
        return _generate_sequential(query, chunks)
    return _generate_single(query, chunks)
