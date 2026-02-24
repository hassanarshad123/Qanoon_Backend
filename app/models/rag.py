from pydantic import BaseModel


class SearchFilters(BaseModel):
    jurisdiction: str | None = None
    court_tier: str | None = None
    courts: list[str] | None = None
    year_from: int | None = None
    year_to: int | None = None
    legal_areas: list[str] | None = None
    statutes_cited: list[str] | None = None
    judge: str | None = None


class SearchRequest(BaseModel):
    query: str
    filters: SearchFilters | None = None
    limit: int = 20
    offset: int = 0


class BrowseRequest(BaseModel):
    filters: SearchFilters | None = None
    sort_by: str = "date"
    sort_order: str = "desc"
    limit: int = 20
    offset: int = 0


class EmbeddingBatchRequest(BaseModel):
    texts: list[str]
