from pydantic import BaseModel


class NoteCreate(BaseModel):
    title: str = "Untitled Note"
    content: str = ""
    folder: str = "General"
    tags: list[str] = []
    source_id: str | None = None
    source_type: str | None = None
    source_label: str | None = None


class NoteContentUpdate(BaseModel):
    content: str


class NoteTitleUpdate(BaseModel):
    title: str


class NoteMetadataUpdate(BaseModel):
    folder: str | None = None
    tags: list[str] | None = None


class FolderCreate(BaseModel):
    name: str
