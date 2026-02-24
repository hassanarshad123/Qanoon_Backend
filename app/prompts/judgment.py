"""Judgment prompts — direct port from lib/ai/prompts/judgment.ts."""

import json


def build_generation_prompt(
    case_data: dict,
    brief_content: str | None,
    rag_results: list[dict],
    judge_profile: dict | None = None,
) -> str:
    precedent_context = "\n".join(
        f"- {r['precedent']['caseName']} ({r['precedent']['citation']}): {r['precedent'].get('ratio', '')}"
        for r in rag_results
    ) if rag_results else "No precedents found."

    judge_info = ""
    if judge_profile:
        judge_info = f"\nJUDGE: {judge_profile.get('designation', 'Justice')} {judge_profile.get('full_name', '')}, {judge_profile.get('court_name', 'Superior Court')}"

    brief_section = f"CASE BRIEF:\n{brief_content}\n" if brief_content else ""

    return f"""You are a senior judicial officer of the Pakistani judiciary drafting a formal judgment.
{judge_info}

CASE DATA:
{json.dumps(case_data, indent=2)}

{brief_section}
RELEVANT PRECEDENTS:
{precedent_context}

Generate EXACTLY 7 sections using XML delimiters:

<section id="header" title="Judgment Header">
[Court name, case number, parties, date, judge]
</section>

<section id="facts" title="Facts of the Case">
[Comprehensive chronological narration of material facts]
</section>

<section id="issues" title="Issues for Determination">
[Numbered legal questions for determination]
</section>

<section id="analysis" title="Analysis & Discussion">
[Detailed analysis of each issue — most comprehensive section]
</section>

<section id="applicable_law" title="Applicable Law">
[List and discuss each applicable statute with specific sections]
</section>

<section id="holding" title="Holding">
[Court's definitive findings on each issue]
</section>

<section id="relief" title="Relief & Order">
[Specific orders, relief granted/denied, directions]
</section>

FORMATTING: Do NOT use markdown formatting. Write in plain text only."""


def build_regeneration_prompt(section_title: str, current_content: str, judge_note: str, context: str) -> str:
    return f"""You are a senior judicial officer. Revise this judgment section per the judge's instructions.

JUDGMENT CONTEXT:
{context}

SECTION TITLE: {section_title}

CURRENT CONTENT:
{current_content}

JUDGE'S INSTRUCTIONS:
{judge_note}

Rewrite incorporating the instructions. Output only the rewritten content.

FORMATTING: Do NOT use markdown formatting. Write in plain text only."""


def build_chat_prompt(context: str, history: list[dict], user_message: str) -> tuple[str, list[dict]]:
    system = f"""You are QanoonAI, a legal assistant for Pakistani judges helping with judgment drafting.

JUDGMENT CONTEXT:
{context}

Answer in formal legal language with proper citations."""

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})

    return system, messages
