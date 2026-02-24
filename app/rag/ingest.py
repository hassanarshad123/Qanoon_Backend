"""Ingestion pipeline for QanoonAI RAG system."""

import asyncio
import json
import logging

from app.repositories.base import fetch_one, fetch_all, execute
from app.services.voyage_client import generate_embeddings
from app.rag.chunking import chunk_judgment
from app.rag.citation_extractor import extract_citations

logger = logging.getLogger(__name__)

EMBEDDING_BATCH_SIZE = 8
EMBEDDING_DELAY_MS = 0.2  # seconds
DB_BATCH_SIZE = 50


async def upsert_judgment(record: dict) -> str:
    legal_areas = record.get("legalAreas", [])
    keywords = record.get("keywords", [])
    headnotes = record.get("headnotes", [])
    statutes_cited = json.dumps(record.get("statutesCited", []))
    metadata = json.dumps(record.get("metadata", {}))

    ts_content = " ".join(filter(None, [
        record.get("caseName"),
        record.get("citation"),
        record.get("summary"),
        record.get("ratio"),
        *(record.get("headnotes") or []),
        *(record.get("keywords") or []),
        record.get("parties"),
        record.get("judgeName"),
    ]))

    row = await fetch_one(
        """INSERT INTO precedents (
            case_name, citation, court, year, legal_areas, keywords, headnotes,
            summary, ratio, jurisdiction, court_tier, judge_name, judgment_date,
            parties, full_text, statutes_cited, source_url, metadata,
            token_count, chunk_strategy, search_vector, ingested_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5::text[], $6::text[], $7::text[],
            $8, $9, $10, $11, $12, $13::date,
            $14, $15, $16::jsonb, $17, $18::jsonb,
            $19, 'pending', to_tsvector('english', $20), now(), now()
        )
        ON CONFLICT (citation) DO UPDATE SET
            case_name = EXCLUDED.case_name, court = EXCLUDED.court, year = EXCLUDED.year,
            legal_areas = EXCLUDED.legal_areas, keywords = EXCLUDED.keywords, headnotes = EXCLUDED.headnotes,
            summary = EXCLUDED.summary, ratio = EXCLUDED.ratio, jurisdiction = EXCLUDED.jurisdiction,
            court_tier = EXCLUDED.court_tier, judge_name = EXCLUDED.judge_name, judgment_date = EXCLUDED.judgment_date,
            parties = EXCLUDED.parties, full_text = EXCLUDED.full_text, statutes_cited = EXCLUDED.statutes_cited,
            source_url = EXCLUDED.source_url, metadata = EXCLUDED.metadata, token_count = EXCLUDED.token_count,
            search_vector = to_tsvector('english', $20), updated_at = now()
        RETURNING id""",
        record.get("caseName"),
        record.get("citation"),
        record.get("court"),
        record.get("year"),
        legal_areas,
        keywords,
        headnotes,
        record.get("summary", ""),
        record.get("ratio", ""),
        record.get("jurisdiction", "PK"),
        record.get("courtTier"),
        record.get("judgeName"),
        record.get("judgmentDate"),
        record.get("parties"),
        record.get("fullText"),
        statutes_cited,
        record.get("sourceUrl"),
        metadata,
        None,  # token_count computed after chunking
        ts_content,
    )
    return str(row["id"])


async def insert_chunks(judgment_id: str, chunks: list) -> None:
    await execute("DELETE FROM case_law_chunks WHERE case_law_id = $1", judgment_id)

    for chunk in chunks:
        await execute(
            """INSERT INTO case_law_chunks (case_law_id, chunk_type, section_label, content, chunk_index, token_count)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            judgment_id,
            chunk.chunk_type,
            chunk.section_label,
            chunk.content,
            chunk.chunk_index,
            chunk.token_count,
        )


async def insert_citations(judgment_id: str, text: str) -> int:
    citations = extract_citations(text)
    if not citations:
        return 0

    await execute("DELETE FROM citation_graph WHERE citing_case_law_id = $1", judgment_id)

    for cite in citations:
        match = await fetch_one(
            "SELECT id FROM precedents WHERE lower(replace(citation, ' ', '')) = $1 LIMIT 1",
            cite.normalized.replace(" ", ""),
        )
        cited_id = str(match["id"]) if match else None

        await execute(
            """INSERT INTO citation_graph (citing_case_law_id, cited_case_law_id, cited_citation, citation_context)
               VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING""",
            judgment_id, cited_id, cite.raw_citation, cite.context,
        )

    return len(citations)


async def embed_documents(judgment_ids: list[str]) -> dict:
    embedded = 0
    failed = 0

    for i in range(0, len(judgment_ids), EMBEDDING_BATCH_SIZE):
        batch = judgment_ids[i:i + EMBEDDING_BATCH_SIZE]
        placeholders = ", ".join(f"${j+1}" for j in range(len(batch)))

        rows = await fetch_all(
            f"SELECT id, case_name, citation, summary, ratio FROM precedents WHERE id IN ({placeholders})",
            *batch,
        )
        texts = [
            f"{r['case_name']}\n{r['citation']}\n{r.get('summary', '')}\n{r.get('ratio', '')}"
            for r in rows
        ]

        try:
            embeddings = await generate_embeddings(texts)
            for j, row in enumerate(rows):
                if j < len(embeddings) and embeddings[j]:
                    emb_str = f"[{','.join(str(v) for v in embeddings[j])}]"
                    await execute(
                        "UPDATE precedents SET embedding = $1::vector WHERE id = $2",
                        emb_str, str(row["id"]),
                    )
                    embedded += 1
                else:
                    failed += 1
        except Exception as e:
            logger.error(f"Embedding batch failed: {e}")
            failed += len(batch)

        if i + EMBEDDING_BATCH_SIZE < len(judgment_ids):
            await asyncio.sleep(EMBEDDING_DELAY_MS)

    return {"embedded": embedded, "failed": failed}


async def embed_chunks(judgment_ids: list[str]) -> dict:
    embedded = 0
    failed = 0

    placeholders = ", ".join(f"${j+1}" for j in range(len(judgment_ids)))
    chunks = await fetch_all(
        f"SELECT id, content FROM case_law_chunks WHERE case_law_id IN ({placeholders}) AND embedding IS NULL",
        *judgment_ids,
    )

    for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[i:i + EMBEDDING_BATCH_SIZE]
        texts = [c["content"] for c in batch]

        try:
            embeddings = await generate_embeddings(texts)
            for j, chunk in enumerate(batch):
                if j < len(embeddings) and embeddings[j]:
                    emb_str = f"[{','.join(str(v) for v in embeddings[j])}]"
                    await execute(
                        "UPDATE case_law_chunks SET embedding = $1::vector WHERE id = $2",
                        emb_str, str(chunk["id"]),
                    )
                    embedded += 1
                else:
                    failed += 1
        except Exception as e:
            logger.error(f"Chunk embedding batch failed: {e}")
            failed += len(batch)

        if i + EMBEDDING_BATCH_SIZE < len(chunks):
            await asyncio.sleep(EMBEDDING_DELAY_MS)

    return {"embedded": embedded, "failed": failed}


async def ingest_judgments(records: list[dict], job_id: str | None = None) -> dict:
    """
    Ingest a batch of judgment records into the RAG system.
    Phases: upsert → chunk → cite → embed documents → embed chunks.
    """
    errors: list[dict] = []
    judgment_ids: list[str] = []
    processed = 0
    chunks_created = 0
    citations_found = 0

    for record in records:
        try:
            jid = await upsert_judgment(record)
            judgment_ids.append(jid)

            result = chunk_judgment(record)
            await insert_chunks(jid, result.chunks)
            chunks_created += len(result.chunks)

            total_tokens = sum(c.token_count for c in result.chunks)
            await execute(
                "UPDATE precedents SET chunk_strategy = $1, token_count = $2 WHERE id = $3",
                result.strategy, total_tokens, jid,
            )

            citation_text = "\n\n".join(filter(None, [
                record.get("fullText"), record.get("summary"), record.get("ratio"),
            ]))
            count = await insert_citations(jid, citation_text)
            citations_found += count

            processed += 1

            if job_id:
                await execute(
                    "UPDATE ingestion_jobs SET processed = $1, last_processed_id = $2 WHERE id = $3",
                    processed, jid, job_id,
                )
        except Exception as e:
            errors.append({"citation": record.get("citation", "unknown"), "error": str(e)})
            logger.error(f"Failed to process {record.get('citation')}: {e}")

    # Embed documents
    doc_embed = await embed_documents(judgment_ids) if judgment_ids else {"embedded": 0, "failed": 0}

    # Embed chunks
    chunk_embed = await embed_chunks(judgment_ids) if judgment_ids else {"embedded": 0, "failed": 0}

    total_embedded = doc_embed["embedded"]
    total_failed = len(errors) + doc_embed["failed"] + chunk_embed["failed"]

    if job_id:
        await execute(
            """UPDATE ingestion_jobs SET
                status = 'completed', processed = $1, embedded = $2,
                failed = $3, error_log = $4::jsonb, completed_at = now()
               WHERE id = $5""",
            processed, total_embedded, total_failed, json.dumps(errors), job_id,
        )

    return {
        "processed": processed,
        "embedded": total_embedded,
        "chunksCreated": chunks_created,
        "citationsFound": citations_found,
        "failed": total_failed,
        "errors": errors,
    }


async def create_ingestion_job(job_type: str, total_records: int, jurisdiction: str | None = None) -> str:
    row = await fetch_one(
        """INSERT INTO ingestion_jobs (job_type, status, jurisdiction, total_records, started_at)
           VALUES ($1, 'running', $2, $3, now()) RETURNING id""",
        job_type, jurisdiction, total_records,
    )
    return str(row["id"])


async def get_ingestion_job_status(job_id: str) -> dict | None:
    row = await fetch_one("SELECT * FROM ingestion_jobs WHERE id = $1", job_id)
    if not row:
        return None

    error_log = row.get("error_log")
    if isinstance(error_log, str):
        try:
            error_log = json.loads(error_log)
        except (json.JSONDecodeError, TypeError):
            error_log = []

    return {
        "id": str(row["id"]),
        "jobType": row.get("job_type"),
        "status": row.get("status"),
        "jurisdiction": row.get("jurisdiction"),
        "totalRecords": row.get("total_records"),
        "processed": row.get("processed"),
        "embedded": row.get("embedded"),
        "failed": row.get("failed"),
        "lastProcessedId": row.get("last_processed_id"),
        "errorLog": error_log,
        "startedAt": row.get("started_at"),
        "completedAt": row.get("completed_at"),
        "createdAt": row.get("created_at"),
    }
