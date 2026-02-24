from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import SessionUser, get_current_user
from app.models.notes import (
    NoteCreate,
    NoteContentUpdate,
    NoteTitleUpdate,
    NoteMetadataUpdate,
    FolderCreate,
)
from app.repositories import notes as notes_repo
from app.repositories import activity as activity_repo

router = APIRouter(tags=["notes"])


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

@router.post("/notes")
async def create_note(
    body: NoteCreate,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    note_id = await notes_repo.create_note(user.id, body.model_dump())
    await activity_repo.log_activity(user.id, "created", "note", note_id, body.title)
    return {"id": note_id}


@router.get("/notes")
async def list_notes(user: Annotated[SessionUser, Depends(get_current_user)]):
    return await notes_repo.list_notes(user.id)


@router.get("/notes/{note_id}")
async def get_note(
    note_id: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    note = await notes_repo.get_note(note_id, user.id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.patch("/notes/{note_id}/content")
async def update_note_content(
    note_id: str,
    body: NoteContentUpdate,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    return await notes_repo.update_note_content(note_id, user.id, body.content)


@router.patch("/notes/{note_id}/title")
async def update_note_title(
    note_id: str,
    body: NoteTitleUpdate,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    return await notes_repo.update_note_title(note_id, user.id, body.title)


@router.patch("/notes/{note_id}/metadata")
async def update_note_metadata(
    note_id: str,
    body: NoteMetadataUpdate,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    await notes_repo.update_note_metadata(note_id, user.id, body.folder, body.tags)
    return {"success": True}


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    await notes_repo.delete_note(note_id, user.id)
    await activity_repo.log_activity(user.id, "deleted", "note", note_id)
    return {"success": True}


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------

@router.get("/folders")
async def list_folders(user: Annotated[SessionUser, Depends(get_current_user)]):
    return await notes_repo.list_folders(user.id)


@router.post("/folders")
async def create_folder(
    body: FolderCreate,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    folder_id = await notes_repo.create_folder(user.id, body.name)
    return {"id": folder_id}


@router.delete("/folders/{name}")
async def delete_folder(
    name: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
):
    await notes_repo.delete_folder(user.id, name)
    return {"success": True}


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

@router.get("/tags")
async def get_tags(user: Annotated[SessionUser, Depends(get_current_user)]):
    return await notes_repo.get_tags()
