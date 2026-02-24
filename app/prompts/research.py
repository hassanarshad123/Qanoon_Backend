"""Research prompts — direct port from lib/ai/prompts/research.ts."""


def build_system_prompt(case_context: dict | None = None) -> str:
    system = """You are QanoonAI, an expert Pakistani legal research assistant serving judges of the Superior Courts.

You MUST structure EVERY response using these EXACT XML tags:

<summary>
A concise 2-4 sentence answer.
</summary>

<applicable_law>
List each relevant statute with specific sections/articles.
</applicable_law>

<precedents>
List relevant case precedents with citation and ratio.
</precedents>

<analysis>
Detailed legal analysis with precise citations.
</analysis>

<contrary_views>
Present contrary judicial opinions or alternative interpretations.
</contrary_views>

INSTRUCTIONS:
- Write in formal legal language for a Pakistani judge
- Cite cases using full citations (e.g., PLD 1988 SC 416)
- Reference specific statutory provisions
- Always include contrary views"""

    if case_context:
        system += f"""

CASE CONTEXT:
- Case: {case_context.get('caseTitle', '')}
- Case Number: {case_context.get('caseNumber', '')}
- Court: {case_context.get('court', '')}"""
        if case_context.get("description"):
            system += f"\n- Description: {case_context['description']}"

    return system


def build_user_message(question: str, rag_results: list[dict], history: list[dict] | None = None) -> list[dict]:
    rag_block = ""
    if rag_results:
        lines = []
        for i, r in enumerate(rag_results):
            p = r.get("precedent", {})
            lines.append(f"{i+1}. {p.get('caseName', '')} ({p.get('citation', '')})\n   Summary: {p.get('summary', '')}\n   Ratio: {p.get('ratio', '')}")
        rag_block = "\n\nRELEVANT PRECEDENTS FROM DATABASE:\n" + "\n\n".join(lines) + "\n\nUse these precedents where relevant."

    messages = []
    if history:
        for m in history:
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question + rag_block})
    return messages


def build_title_prompt(question: str) -> str:
    return f"""Generate a concise 5-8 word title for a legal research conversation: "{question}"

Return ONLY the title — no quotes, no explanation."""
