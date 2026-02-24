from pydantic import BaseModel


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: str


class RagIngestRequest(BaseModel):
    records: list[dict] = []
    record: dict | None = None


class RagBulkIngestRequest(BaseModel):
    records: list[dict]
    jurisdiction: str | None = None


class RagQueryRequest(BaseModel):
    query: str
    filters: dict | None = None
    limit: int = 10
    include_chunks: bool = False
