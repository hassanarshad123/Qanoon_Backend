from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import SessionUser, get_current_user
from app.models.rag import SearchRequest, BrowseRequest, EmbeddingBatchRequest
from app.rag.service import search, browse, get_case_law
from app.services.voyage_client import generate_embeddings

router = APIRouter(tags=["case-law"])


@router.post("/case-law/search")
async def search_case_law(
    body: SearchRequest,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    if len(body.query.strip()) < 3:
        raise HTTPException(status_code=400, detail="Query must be at least 3 characters")

    filters = body.filters.model_dump(exclude_none=True) if body.filters else None

    results = await search({
        "query": body.query,
        "filters": filters,
        "limit": body.limit,
        "offset": body.offset,
    })

    return {
        "query": body.query,
        "result_count": len(results),
        "results": results,
    }


@router.post("/case-law/browse")
async def browse_case_law(
    body: BrowseRequest,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    filters = body.filters.model_dump(exclude_none=True) if body.filters else None

    result = await browse({
        "filters": filters,
        "sort_by": body.sort_by,
        "sort_order": body.sort_order,
        "limit": body.limit,
        "offset": body.offset,
    })

    return result


@router.get("/case-law/{case_id}")
async def get_case_law_by_id(
    case_id: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    case = await get_case_law(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("/embeddings/batch")
async def batch_embeddings(
    body: EmbeddingBatchRequest,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    embeddings = await generate_embeddings(body.texts)
    return {"embeddings": embeddings}
