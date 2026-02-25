import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.auth import SessionUser, require_role
from app.models.documents import DocumentLinkUpdate
from app.repositories import documents as docs_repo
from app.repositories import activity as activity_repo
from app.services.storage_service import upload_file, delete_file

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/upload", status_code=201)
async def upload_document(
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
    file: UploadFile = File(...),
    title: str = Form("Untitled"),
    document_type: str = Form("Other"),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 50MB.")

    key = f"judges/{user.id}/{int(time.time())}-{file.filename}"
    blob_url = await upload_file(key, data, file.content_type or "application/octet-stream")

    doc_id = await docs_repo.create_document(user.id, {
        "title": title or file.filename,
        "file_name": file.filename,
        "file_type": file.content_type or "application/octet-stream",
        "file_size": len(data),
        "document_type": document_type,
        "blob_url": blob_url,
        "blob_pathname": key,
    })

    await activity_repo.log_activity(user.id, "created", "document", doc_id, title)

    return {"id": doc_id, "blob_url": blob_url, "file_name": file.filename}


@router.get("")
async def list_documents(
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
    document_type: str | None = Query(None),
    search: str | None = Query(None),
):
    return await docs_repo.list_documents(user.id, document_type, search)


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    doc = await docs_repo.get_document(doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    result = await docs_repo.delete_document(doc_id, user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from S3 (best effort)
    try:
        await delete_file(result["blob_url"])
    except Exception:
        pass

    await activity_repo.log_activity(user.id, "deleted", "document", doc_id)
    return {"success": True}


@router.patch("/{doc_id}/link")
async def link_document(
    doc_id: str,
    body: DocumentLinkUpdate,
    user: Annotated[SessionUser, Depends(require_role("judge", "lawyer", "admin"))],
):
    doc = await docs_repo.get_document(doc_id, user.id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await docs_repo.link_document(doc_id, user.id, body.brief_id, body.judgment_id)
    return {"success": True}
