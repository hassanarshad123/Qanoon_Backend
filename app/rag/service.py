"""
Hybrid RAG search service — vector + full-text + metadata scoring.
Direct port of lib/rag/service.ts to Python/asyncpg.
"""

import json

from app.repositories.base import fetch_all, fetch_one
from app.services.voyage_client import generate_embedding
from app.rag.cache import build_cache_key, get_cached, set_cache

DEFAULT_WEIGHTS = {"vector": 0.6, "full_text": 0.25, "metadata": 0.15}


def _parse_array(val) -> list[str]:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        if val.startswith("{") and val.endswith("}"):
            inner = val[1:-1]
            if not inner:
                return []
            return [s.strip().strip('"') for s in inner.split(",")]
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _row_to_judgment(r) -> dict:
    return {
        "id": str(r["id"]),
        "case_name": r["case_name"],
        "citation": r["citation"],
        "court": r["court"],
        "year": r["year"],
        "legal_areas": _parse_array(r.get("legal_areas")),
        "keywords": _parse_array(r.get("keywords")),
        "headnotes": _parse_array(r.get("headnotes")),
        "summary": r.get("summary", ""),
        "ratio": r.get("ratio", ""),
        "jurisdiction": r.get("jurisdiction", "PK"),
        "court_tier": r.get("court_tier"),
        "judge_name": r.get("judge_name"),
        "judgment_date": str(r["judgment_date"]) if r.get("judgment_date") else None,
        "parties": r.get("parties"),
        "statutes_cited": _parse_array(r.get("statutes_cited")),
        "source_url": r.get("source_url"),
        "token_count": r.get("token_count"),
        "metadata": json.loads(r["metadata"]) if isinstance(r.get("metadata"), str) else r.get("metadata"),
    }


def _build_filter_clauses(filters: dict | None, start_idx: int) -> tuple[list[str], list, int]:
    clauses: list[str] = []
    params: list = []
    idx = start_idx

    if not filters:
        return clauses, params, idx

    if filters.get("jurisdiction"):
        clauses.append(f"p.jurisdiction = ${idx}")
        params.append(filters["jurisdiction"])
        idx += 1
    if filters.get("court_tier"):
        clauses.append(f"p.court_tier = ${idx}")
        params.append(filters["court_tier"])
        idx += 1
    if filters.get("courts"):
        clauses.append(f"p.court = ANY(${idx})")
        params.append(filters["courts"])
        idx += 1
    if filters.get("year_from"):
        clauses.append(f"p.year >= ${idx}")
        params.append(filters["year_from"])
        idx += 1
    if filters.get("year_to"):
        clauses.append(f"p.year <= ${idx}")
        params.append(filters["year_to"])
        idx += 1
    if filters.get("legal_areas"):
        clauses.append(f"p.legal_areas && ${idx}::text[]")
        params.append(filters["legal_areas"])
        idx += 1
    if filters.get("judge"):
        clauses.append(f"p.judge_name ILIKE ${idx}")
        params.append(f"%{filters['judge']}%")
        idx += 1

    return clauses, params, idx


def _build_ts_query(query: str) -> str:
    import re
    tokens = re.sub(r"[^a-zA-Z0-9\s]", " ", query).split()
    return " | ".join(t for t in tokens if len(t) > 2)[:500]


async def search(options: dict) -> list[dict]:
    query = options["query"]
    filters = options.get("filters")
    limit = options.get("limit", 10)
    offset = options.get("offset", 0)
    weights = {**DEFAULT_WEIGHTS, **(options.get("weights") or {})}

    cache_key = build_cache_key(options)
    cached = await get_cached(cache_key)
    if cached:
        return cached

    embedding = await generate_embedding(query)
    ts_query = _build_ts_query(query)

    clauses, params, idx = _build_filter_clauses(filters, 1)
    where_base = (" AND ".join(clauses) + " AND ") if clauses else ""

    query_params = list(params)
    score_parts = []

    if embedding and ts_query.strip():
        emb_str = "[" + ",".join(str(x) for x in embedding) + "]"
        query_params.append(emb_str)
        emb_idx = idx
        idx += 1
        query_params.append(ts_query)
        ts_idx = idx
        idx += 1

        score_parts.append(f"(1 - (p.embedding <=> ${emb_idx}::vector)) * {weights['vector']}")
        score_parts.append(f"COALESCE(ts_rank(p.search_vector, to_tsquery('english', ${ts_idx})), 0) * {weights['full_text']}")
        score_parts.append(f"""(CASE p.court_tier
            WHEN 'supreme' THEN 1.0 WHEN 'high' THEN 0.7
            WHEN 'appellate' THEN 0.5 WHEN 'district' THEN 0.3
            WHEN 'tribunal' THEN 0.2 ELSE 0.4 END) * {weights['metadata']}""")

        score_expr = " + ".join(score_parts)
        query_params.append(limit)
        lim_idx = idx
        idx += 1
        query_params.append(offset)
        off_idx = idx

        rows = await fetch_all(
            f"""SELECT p.*, ({score_expr}) AS score FROM precedents p
                WHERE {where_base} p.embedding IS NOT NULL
                ORDER BY score DESC LIMIT ${lim_idx} OFFSET ${off_idx}""",
            *query_params,
        )
    elif embedding:
        emb_str = "[" + ",".join(str(x) for x in embedding) + "]"
        query_params.append(emb_str)
        emb_idx = idx
        idx += 1
        query_params.append(limit)
        lim_idx = idx
        idx += 1
        query_params.append(offset)
        off_idx = idx

        rows = await fetch_all(
            f"""SELECT p.*, (1 - (p.embedding <=> ${emb_idx}::vector)) AS score FROM precedents p
                WHERE {where_base} p.embedding IS NOT NULL
                ORDER BY p.embedding <=> ${emb_idx}::vector LIMIT ${lim_idx} OFFSET ${off_idx}""",
            *query_params,
        )
    elif ts_query.strip():
        query_params.append(ts_query)
        ts_idx = idx
        idx += 1
        query_params.append(limit)
        lim_idx = idx
        idx += 1
        query_params.append(offset)
        off_idx = idx

        rows = await fetch_all(
            f"""SELECT p.*, ts_rank(p.search_vector, to_tsquery('english', ${ts_idx})) AS score FROM precedents p
                WHERE {where_base} p.search_vector @@ to_tsquery('english', ${ts_idx})
                ORDER BY score DESC LIMIT ${lim_idx} OFFSET ${off_idx}""",
            *query_params,
        )
    else:
        query_params.append(limit)
        lim_idx = idx
        idx += 1
        query_params.append(offset)
        off_idx = idx
        where_str = f"WHERE {where_base.rstrip(' AND ')}" if where_base else ""

        rows = await fetch_all(
            f"""SELECT p.*, 0.5 AS score FROM precedents p {where_str}
                ORDER BY p.year DESC LIMIT ${lim_idx} OFFSET ${off_idx}""",
            *query_params,
        )

    results = []
    for r in rows:
        j = _row_to_judgment(r)
        score = float(r.get("score", 0.5))
        results.append({
            "judgment": j,
            "relevance_score": round(score * 100),
            "matched_keywords": j["keywords"][:5],
            "matched_areas": j["legal_areas"],
        })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    final = results[:limit]

    await set_cache(cache_key, final)
    return final


async def browse(options: dict) -> dict:
    filters = options.get("filters")
    sort_by = options.get("sort_by", "date")
    sort_order = options.get("sort_order", "desc")
    limit = options.get("limit", 20)
    offset = options.get("offset", 0)

    clauses, params, idx = _build_filter_clauses(filters, 1)
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    order_map = {"date": "p.judgment_date", "year": "p.year", "court": "p.court", "relevance": "p.year"}
    order_col = order_map.get(sort_by, "p.year")
    direction = "ASC" if sort_order == "asc" else "DESC"

    count_row = await fetch_one(f"SELECT count(*) AS total FROM precedents p {where_clause}", *params)
    total = int(count_row["total"]) if count_row else 0

    page_params = list(params)
    page_params.append(limit)
    lim_idx = idx
    page_params.append(offset)
    off_idx = idx + 1

    rows = await fetch_all(
        f"""SELECT p.* FROM precedents p {where_clause}
            ORDER BY {order_col} {direction} NULLS LAST
            LIMIT ${lim_idx} OFFSET ${off_idx}""",
        *page_params,
    )

    return {
        "judgments": [_row_to_judgment(r) for r in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


async def get_case_law(case_id: str) -> dict | None:
    row = await fetch_one("SELECT p.* FROM precedents p WHERE p.id = $1", case_id)
    if not row:
        return None
    return _row_to_judgment(row)
