"""Precedent ranking prompt."""


def build_ranking_prompt(case_data: dict, search_results: list[dict]) -> str:
    precedents = "\n\n".join(
        f"{i+1}. {p['caseName']} ({p['citation']})\n   Areas: {', '.join(p.get('legalAreas', []))}\n   Summary: {p.get('summary', '')}\n   Ratio: {p.get('ratio', '')}"
        for i, p in enumerate(search_results)
    )

    return f"""You are a Pakistani legal research expert. Rank the precedents by relevance.

CASE DETAILS:
- Legal Issues: {'; '.join(case_data.get('legalIssues', []))}
- Applicable Statutes: {'; '.join(case_data.get('statutes', []))}
- Case Type: {case_data.get('caseType', '')}

CANDIDATE PRECEDENTS:
{precedents}

Return a JSON array sorted by relevance (most relevant first):
[{{"id": "string", "relevanceScore": 0-100, "matchedKeywords": ["string"], "matchedAreas": ["string"], "explanation": "string"}}]"""
