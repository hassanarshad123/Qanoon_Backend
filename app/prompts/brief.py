"""Brief generation and analysis prompts — direct port from lib/ai/prompts/brief.ts."""

import json


def build_analysis_prompt(
    document_texts: list[dict],
    chunk_index: int | None = None,
    total_chunks: int | None = None,
) -> str:
    docs = "\n\n".join(
        f"--- DOCUMENT {i+1}: {d['fileName']} ---\n{d['text']}"
        for i, d in enumerate(document_texts)
    )
    chunk_note = ""
    if total_chunks and total_chunks > 1:
        chunk_note = f"\n\nNOTE: This is batch {(chunk_index or 0) + 1} of {total_chunks}. Extract all information from THESE documents only.\n"

    return f"""You are a senior Pakistani legal expert with deep expertise in constitutional, civil, criminal, family, tax, and corporate law. Analyze the following court documents thoroughly and extract structured data.

Be exhaustive — identify every party, every legal issue, every statute reference, every argument made by each side.{chunk_note}

DOCUMENTS:
{docs}

Return a JSON object with EXACTLY this structure (no markdown, no code fences, just raw JSON):
{{
  "courtInfo": {{
    "courtName": "string", "caseNumber": "string", "caseType": "string",
    "filingDate": "string or null", "judge": "string or null"
  }},
  "parties": [{{"name": "string", "role": "petitioner | respondent | appellant | other", "counsel": "string or null"}}],
  "facts": [{{"content": "string", "date": "string or null", "order": 0}}],
  "legalIssues": [{{"content": "string", "relatedStatutes": ["string"]}}],
  "statutes": [{{"name": "string", "provisions": ["string"], "context": "string"}}],
  "arguments": [{{"content": "string", "side": "petitioner | respondent", "supportingCitations": ["string"]}}]
}}"""


def build_generation_prompt(extracted_data: dict, rag_results: list[dict]) -> str:
    precedent_context = "\n".join(
        f"- {r['precedent']['caseName']} ({r['precedent']['citation']}): {r['precedent'].get('ratio', '')} [Relevance: {r.get('relevanceScore', 0)}%]"
        for r in rag_results
    ) if rag_results else "No precedents found."

    return f"""You are a senior judicial clerk preparing a comprehensive case brief for a Pakistani High Court judge. Generate a thorough, well-structured case brief using the extracted case data and relevant precedents below.

EXTRACTED CASE DATA:
{json.dumps(extracted_data, indent=2)}

RELEVANT PRECEDENTS:
{precedent_context}

Generate EXACTLY 10 sections using XML delimiters. Each section must be comprehensive with proper legal formatting and reasoning.

<section id="case_header" title="Case Header">
[Court name, case number, case type, parties vs parties, date]
</section>

<section id="parties" title="Parties & Representation">
[Full details of each party, their role, and their counsel/advocate]
</section>

<section id="material_facts" title="Material Facts">
[Numbered list of material facts in chronological order]
</section>

<section id="legal_issues" title="Legal Issues">
[Numbered list of legal questions the court must determine]
</section>

<section id="statutes" title="Applicable Statutes">
[List each applicable statute with section/article numbers]
</section>

<section id="petitioner_arguments" title="Petitioner's Arguments">
[Numbered list of arguments with supporting citations]
</section>

<section id="respondent_arguments" title="Respondent's Arguments">
[Numbered list of arguments with supporting citations]
</section>

<section id="precedents" title="Relevant Precedents">
[For each precedent: number. Case Name (Citation): Brief explanation]
</section>

<section id="comparative_matrix" title="Comparative Matrix">
[Compare petitioner's and respondent's positions side by side]
</section>

<section id="analysis" title="Preliminary Analysis">
[Comprehensive judicial analysis — most detailed section]
</section>

FORMATTING: Do NOT use markdown formatting. No **, no *, no ##. Write in plain text only."""


def build_regeneration_prompt(section_title: str, current_content: str, judge_note: str, brief_context: str) -> str:
    return f"""You are a senior judicial clerk. A judge has reviewed a section of a case brief and provided feedback.

BRIEF CONTEXT:
{brief_context}

SECTION TITLE: {section_title}

CURRENT CONTENT:
{current_content}

JUDGE'S FEEDBACK:
{judge_note}

Rewrite the section incorporating the judge's instructions. Output only the rewritten section content.

FORMATTING: Do NOT use markdown formatting. Write in plain text only."""


def build_chat_prompt(brief_context: str, history: list[dict], user_message: str) -> tuple[str, list[dict]]:
    system = f"""You are QanoonAI, a legal research assistant for Pakistani judges.

BRIEF CONTEXT:
{brief_context}

Answer in formal but clear legal language with proper citations."""

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})

    return system, messages
