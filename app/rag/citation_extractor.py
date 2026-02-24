"""Citation graph builder for Pakistani and UK court judgments."""

import re
from dataclasses import dataclass


@dataclass
class ExtractedCitation:
    raw_citation: str
    normalized: str
    context: str


# Pakistani law reports
PK_CITATION_REGEX = re.compile(
    r"(?:"
    r"PLD\s+\d{4}\s+(?:SC|Lah|Kar|Pesh|Quetta|Isb|FSC|AJK)\s+\d+"
    r"|"
    r"\d{4}\s+(?:SCMR|CLC|PCrLJ|YLR|MLD|PLJ|NLR|ALD|PSC|PLC|GBLR|PTD|FTR|TTR)\s+\d+"
    r"|"
    r"\d{4}\s+(?:CLC|PCrLJ|YLR|MLD|PLJ)\s+\d+\s+(?:Lah|Kar|Pesh|Quetta|Isb|Bal)"
    r")",
    re.IGNORECASE,
)

# UK neutral + law report citations
UK_CITATION_REGEX = re.compile(
    r"(?:"
    r"\[\d{4}\]\s+(?:UKSC|UKHL|UKPC|EWCA\s+(?:Civ|Crim)|EWHC(?:\s+\d+)?(?:\s*\((?:QB|Ch|Fam|Admin|Comm|Pat|TCC|IPEC)\))?)\s+\d+"
    r"|"
    r"\[\d{4}\]\s+(?:\d+\s+)?(?:AC|QB|WLR|All\s*ER|Ch|Fam|ICR|IRLR|Lloyd'?s\s*Rep)\s+\d+"
    r")",
    re.IGNORECASE,
)


def normalize_citation(citation: str) -> str:
    return re.sub(r"\s+", " ", citation.strip().replace("[", "").replace("]", "")).lower()


def extract_citations(text: str) -> list[ExtractedCitation]:
    if not text or not text.strip():
        return []

    citations: list[ExtractedCitation] = []
    seen: set[str] = set()

    for pattern in [PK_CITATION_REGEX, UK_CITATION_REGEX]:
        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            norm = normalize_citation(raw)
            if norm in seen:
                continue
            seen.add(norm)

            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = re.sub(r"\s+", " ", text[start:end]).strip()

            citations.append(ExtractedCitation(
                raw_citation=raw,
                normalized=norm,
                context=context,
            ))

    return citations
