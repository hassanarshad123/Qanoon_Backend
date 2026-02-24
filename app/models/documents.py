from pydantic import BaseModel


class DocumentLinkUpdate(BaseModel):
    brief_id: str | None = None
    judgment_id: str | None = None
