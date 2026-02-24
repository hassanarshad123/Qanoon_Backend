import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.core.auth import SessionUser, require_admin
from app.models.admin import (
    RagBulkIngestRequest,
    RagIngestRequest,
    RagQueryRequest,
    UserRoleUpdate,
    UserStatusUpdate,
)
from app.repositories import admin as admin_repo
from app.repositories.base import fetch_one, fetch_all

router = APIRouter(prefix="/admin", tags=["admin"])


# --------------- User management ---------------


@router.get("/stats")
async def get_stats(user: Annotated[SessionUser, Depends(require_admin)]):
    return await admin_repo.get_stats()


@router.get("/users")
async def get_users(
    user: Annotated[SessionUser, Depends(require_admin)],
    search: str | None = Query(None),
    role: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
):
    return await admin_repo.get_users(search, role, status, page, page_size)


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    user: Annotated[SessionUser, Depends(require_admin)],
):
    detail = await admin_repo.get_user_detail(user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="User not found")
    return detail


@router.patch("/users/{user_id}/status")
async def toggle_user_status(
    user_id: str,
    body: UserStatusUpdate,
    user: Annotated[SessionUser, Depends(require_admin)],
):
    await admin_repo.toggle_user_status(user_id, body.is_active)
    return {"success": True}


@router.patch("/users/{user_id}/role")
async def change_user_role(
    user_id: str,
    body: UserRoleUpdate,
    user: Annotated[SessionUser, Depends(require_admin)],
):
    try:
        await admin_repo.change_user_role(user_id, body.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True}


# --------------- RAG management ---------------


@router.post("/rag/ingest")
async def rag_ingest(
    body: RagIngestRequest,
    user: Annotated[SessionUser, Depends(require_admin)],
):
    from app.rag.ingest import create_ingestion_job, ingest_judgments

    records = body.records if body.records else ([body.record] if body.record else [])
    if not records:
        raise HTTPException(status_code=400, detail="No records provided")
    if len(records) > 100:
        raise HTTPException(status_code=400, detail="Too many records. Use /admin/rag/ingest/bulk for >100.")

    job_id = await create_ingestion_job("incremental", len(records))
    result = await ingest_judgments(records, job_id)

    return {"success": True, "jobId": job_id, **result}


@router.get("/rag/ingest")
async def get_ingest_status(
    user: Annotated[SessionUser, Depends(require_admin)],
    job_id: str = Query(alias="jobId"),
):
    from app.rag.ingest import get_ingestion_job_status

    status = await get_ingestion_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@router.post("/rag/ingest/bulk")
async def rag_ingest_bulk(
    body: RagBulkIngestRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[SessionUser, Depends(require_admin)],
):
    from app.rag.ingest import create_ingestion_job, ingest_judgments

    if not body.records:
        raise HTTPException(status_code=400, detail="No records provided")

    job_id = await create_ingestion_job("bulk", len(body.records), body.jurisdiction)

    # Run ingestion in the background (truly async in FastAPI!)
    background_tasks.add_task(ingest_judgments, body.records, job_id)

    return {
        "success": True,
        "jobId": job_id,
        "message": f"Bulk ingestion started for {len(body.records)} records. Poll /admin/rag/ingest?jobId={job_id} for status.",
    }


@router.post("/rag/query")
async def rag_query(
    body: RagQueryRequest,
    user: Annotated[SessionUser, Depends(require_admin)],
):
    from app.rag.service import search as rag_search

    if len(body.query.strip()) < 10:
        raise HTTPException(status_code=400, detail="Query must be at least 10 characters")

    start = time.time()
    results = await rag_search({
        "query": body.query,
        "filters": body.filters,
        "limit": body.limit,
    })
    response_time_ms = round((time.time() - start) * 1000)

    return {
        "query": body.query,
        "resultCount": len(results),
        "results": [
            {
                "judgment": {
                    "id": r.get("judgment", r).get("id", ""),
                    "caseName": r.get("judgment", r).get("caseName", r.get("judgment", r).get("case_name", "")),
                    "citation": r.get("judgment", r).get("citation", ""),
                    "court": r.get("judgment", r).get("court", ""),
                    "year": r.get("judgment", r).get("year"),
                    "legalAreas": r.get("judgment", r).get("legalAreas", r.get("judgment", r).get("legal_areas", [])),
                    "courtTier": r.get("judgment", r).get("courtTier", r.get("judgment", r).get("court_tier", "")),
                    "jurisdiction": r.get("judgment", r).get("jurisdiction", ""),
                },
                "relevanceScore": r.get("relevanceScore", r.get("score", 0)),
                "matchedKeywords": r.get("matchedKeywords", []),
                "matchedAreas": r.get("matchedAreas", []),
            }
            for r in results
        ],
        "responseTimeMs": response_time_ms,
    }


@router.get("/rag/health")
async def rag_health(user: Annotated[SessionUser, Depends(require_admin)]):
    start = time.time()

    try:
        count_row = await fetch_one(
            "SELECT count(*) AS total, count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded FROM precedents"
        )
        chunk_row = await fetch_one(
            "SELECT count(*) AS total, count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded FROM case_law_chunks"
        )
        latest_job = await fetch_one(
            "SELECT id, status, processed, embedded, failed, completed_at FROM ingestion_jobs ORDER BY created_at DESC LIMIT 1"
        )

        response_time_ms = round((time.time() - start) * 1000)

        return {
            "status": "ok",
            "source": "neon_pgvector",
            "judgments": {
                "total": int(count_row["total"] or 0),
                "embedded": int(count_row["embedded"] or 0),
            },
            "chunks": {
                "total": int(chunk_row["total"] or 0),
                "embedded": int(chunk_row["embedded"] or 0),
            },
            "lastIngestion": {
                "id": str(latest_job["id"]),
                "status": latest_job["status"],
                "processed": latest_job.get("processed"),
                "embedded": latest_job.get("embedded"),
                "failed": latest_job.get("failed"),
                "completedAt": latest_job["completed_at"].isoformat() if latest_job.get("completed_at") else None,
            } if latest_job else None,
            "responseTimeMs": response_time_ms,
        }
    except Exception as e:
        response_time_ms = round((time.time() - start) * 1000)
        return {"status": "error", "error": str(e), "responseTimeMs": response_time_ms}


@router.get("/rag/info")
async def rag_info(user: Annotated[SessionUser, Depends(require_admin)]):
    try:
        stats = await fetch_one("""
            SELECT
                count(*) AS total_judgments,
                count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded_judgments,
                count(DISTINCT jurisdiction) AS jurisdictions,
                count(DISTINCT court_tier) FILTER (WHERE court_tier IS NOT NULL) AS court_tiers,
                min(year) AS earliest_year,
                max(year) AS latest_year
            FROM precedents
        """)

        chunk_stats = await fetch_one("""
            SELECT count(*) AS total_chunks,
                   count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded_chunks
            FROM case_law_chunks
        """)

        citation_stats = await fetch_one("""
            SELECT count(*) AS total_links,
                   count(*) FILTER (WHERE cited_case_law_id IS NOT NULL) AS resolved_links
            FROM citation_graph
        """)

        jurisdictions = await fetch_all("""
            SELECT jurisdiction, count(*) AS count FROM precedents GROUP BY jurisdiction ORDER BY count DESC
        """)

        court_tiers = await fetch_all("""
            SELECT court_tier, count(*) AS count FROM precedents WHERE court_tier IS NOT NULL GROUP BY court_tier ORDER BY count DESC
        """)

        latest_job = await fetch_one("""
            SELECT id, job_type, status, total_records, processed, embedded, failed, started_at, completed_at
            FROM ingestion_jobs ORDER BY created_at DESC LIMIT 1
        """)

        total = int(stats["total_judgments"] or 0)
        embedded = int(stats["embedded_judgments"] or 0)

        return {
            "source": "neon_pgvector",
            "judgments": {
                "total": total,
                "embedded": embedded,
                "coverage": round((embedded / total) * 100) if total > 0 else 0,
            },
            "chunks": {
                "total": int(chunk_stats["total_chunks"] or 0),
                "embedded": int(chunk_stats["embedded_chunks"] or 0),
            },
            "citations": {
                "totalLinks": int(citation_stats["total_links"] or 0),
                "resolvedLinks": int(citation_stats["resolved_links"] or 0),
            },
            "yearRange": {
                "from": stats.get("earliest_year"),
                "to": stats.get("latest_year"),
            },
            "jurisdictionBreakdown": [
                {"jurisdiction": r["jurisdiction"], "count": int(r["count"])}
                for r in jurisdictions
            ],
            "courtTierBreakdown": [
                {"courtTier": r["court_tier"], "count": int(r["count"])}
                for r in court_tiers
            ],
            "lastIngestion": {
                "id": str(latest_job["id"]),
                "jobType": latest_job.get("job_type"),
                "status": latest_job.get("status"),
                "totalRecords": latest_job.get("total_records"),
                "processed": latest_job.get("processed"),
                "embedded": latest_job.get("embedded"),
                "failed": latest_job.get("failed"),
                "startedAt": latest_job["started_at"].isoformat() if latest_job.get("started_at") else None,
                "completedAt": latest_job["completed_at"].isoformat() if latest_job.get("completed_at") else None,
            } if latest_job else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
