from pydantic import BaseModel


class ActivityEntry(BaseModel):
    id: str
    action: str
    entity_type: str
    entity_id: str | None = None
    entity_title: str | None = None
    metadata: dict = {}
    created_at: str
