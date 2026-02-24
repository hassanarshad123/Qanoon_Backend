"""Smart legal document chunker for Pakistani/UK court judgments."""

import math
import re
from dataclasses import dataclass


@dataclass
class ChunkRecord:
    chunk_type: str  # 'summary' | 'section' | 'paragraph'
    section_label: str | None
    content: str
    chunk_index: int
    token_count: int


@dataclass
class ChunkingResult:
    chunks: list[ChunkRecord]
    strategy: str  # 'document_only' | 'document_and_sections' | 'document_and_paragraphs'


# Section heading patterns (Pakistani + UK)
PK_SECTION_PATTERNS = [
    re.compile(r"^(?:FACTS?|STATEMENT OF FACTS?)\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:ISSUES?|QUESTIONS? (?:OF LAW|FOR DETERMINATION))\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:ARGUMENTS?|SUBMISSIONS?|CONTENTIONS?)\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:ARGUMENTS? (?:ON BEHALF|BY) (?:(?:THE )?PETITIONER|(?:THE )?APPELLANT))\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:ARGUMENTS? (?:ON BEHALF|BY) (?:(?:THE )?RESPONDENT|(?:THE )?STATE))\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:HOLDING|DECISION|JUDGMENT|FINDINGS?)\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:RATIO DECIDENDI|RATIO)\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:ORDER|SHORT ORDER|OPERATIVE ORDER)\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:DISSENT(?:ING)?|MINORITY)(?: OPINION| VIEW| NOTE)?\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:CONCURR(?:ING|ENCE))(?: OPINION| NOTE)?\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:ANALYSIS|DISCUSSION|REASONING)\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:RELIEF|PRAYER|DISPOSITION)\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:PRELIMINARY|BACKGROUND|INTRODUCTION|PREAMBLE)\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:APPLICABLE LAW|RELEVANT (?:LAW|PROVISIONS?|STATUT(?:E|ORY) PROVISIONS?))\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:PRECEDENTS?|CASE LAW|AUTHORITIES?)\s*[:\-.]?\s*$", re.IGNORECASE | re.MULTILINE),
]

UK_SECTION_PATTERNS = [
    re.compile(r"^(?:INTRODUCTION|BACKGROUND)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:THE FACTS?|FACTUAL BACKGROUND)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:THE (?:LEGAL |STATUTORY )?FRAMEWORK)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:THE ISSUES?|ISSUES? ARISING)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:(?:THE )?SUBMISSIONS?)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:DISCUSSION|ANALYSIS|REASONING)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:(?:THE )?JUDGMENT|DECISION|CONCLUSION)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:DISPOSITION|RESULT|ORDER)\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:LORD|LADY)\s+\w+\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:DISSENTING|CONCURRING)\s+(?:JUDGMENT|OPINION)\s*$", re.IGNORECASE | re.MULTILINE),
]

ALL_SECTION_PATTERNS = PK_SECTION_PATTERNS + UK_SECTION_PATTERNS

MAX_SECTION_TOKENS = 1500
OVERLAP_TOKENS = 150
MIN_SECTIONS_FOR_STRUCTURED = 3


def _estimate_tokens(text: str) -> int:
    return math.ceil(len(text.split()) * 1.3)


def _detect_sections(text: str) -> list[tuple[str, str]]:
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    current_label = "Preamble"
    current_lines: list[str] = []

    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            current_lines.append("")
            continue

        is_heading = False
        heading_label = ""

        for pattern in ALL_SECTION_PATTERNS:
            if pattern.match(trimmed):
                is_heading = True
                heading_label = re.sub(r"[:\-.\s]+$", "", trimmed).strip()
                break

        if is_heading:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append((current_label, content))
            current_label = heading_label
            current_lines = []
        else:
            current_lines.append(line)

    content = "\n".join(current_lines).strip()
    if content:
        sections.append((current_label, content))

    return sections


def _split_into_paragraph_chunks(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = _estimate_tokens(para)

        if current_tokens + para_tokens > max_tokens and current_chunk:
            chunks.append("\n\n".join(current_chunk))

            overlap_chunk: list[str] = []
            overlap_count = 0
            for item in reversed(current_chunk):
                t = _estimate_tokens(item)
                if overlap_count + t > overlap_tokens:
                    break
                overlap_chunk.insert(0, item)
                overlap_count += t
            current_chunk = overlap_chunk
            current_tokens = overlap_count

        current_chunk.append(para)
        current_tokens += para_tokens

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def chunk_judgment(record: dict) -> ChunkingResult:
    chunks: list[ChunkRecord] = []
    chunk_index = 0

    # 1. Document-level summary chunk
    summary_parts = [
        record.get("caseName", ""),
        record.get("citation", ""),
        record.get("summary", ""),
        record.get("ratio", ""),
        *[h for h in (record.get("headnotes") or [])],
        ", ".join(record.get("keywords") or []),
    ]
    summary_text = "\n\n".join(p for p in summary_parts if p)
    chunks.append(ChunkRecord(
        chunk_type="summary",
        section_label=None,
        content=summary_text,
        chunk_index=chunk_index,
        token_count=_estimate_tokens(summary_text),
    ))
    chunk_index += 1

    full_text = (record.get("fullText") or "").strip()
    if not full_text:
        return ChunkingResult(chunks=chunks, strategy="document_only")

    # 2. Detect sections
    sections = _detect_sections(full_text)

    if len(sections) >= MIN_SECTIONS_FOR_STRUCTURED:
        for label, content in sections:
            section_tokens = _estimate_tokens(content)
            if section_tokens <= MAX_SECTION_TOKENS:
                chunks.append(ChunkRecord(
                    chunk_type="section",
                    section_label=label,
                    content=content,
                    chunk_index=chunk_index,
                    token_count=section_tokens,
                ))
                chunk_index += 1
            else:
                for pc in _split_into_paragraph_chunks(content, MAX_SECTION_TOKENS, OVERLAP_TOKENS):
                    chunks.append(ChunkRecord(
                        chunk_type="paragraph",
                        section_label=label,
                        content=pc,
                        chunk_index=chunk_index,
                        token_count=_estimate_tokens(pc),
                    ))
                    chunk_index += 1
        return ChunkingResult(chunks=chunks, strategy="document_and_sections")

    # 3. Fallback: paragraph-level chunks
    for pc in _split_into_paragraph_chunks(full_text, MAX_SECTION_TOKENS, OVERLAP_TOKENS):
        chunks.append(ChunkRecord(
            chunk_type="paragraph",
            section_label=None,
            content=pc,
            chunk_index=chunk_index,
            token_count=_estimate_tokens(pc),
        ))
        chunk_index += 1

    return ChunkingResult(chunks=chunks, strategy="document_and_paragraphs")
