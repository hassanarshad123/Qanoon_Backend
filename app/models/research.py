from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str = "New Research"
    case_id: str | None = None
    mode: str = "general"


class ConversationMetaUpdate(BaseModel):
    legal_areas: list[str] | None = None
    case_id: str | None = None


class MessageCreate(BaseModel):
    role: str
    content: str
    structured_response: dict | None = None
    citations: list[dict] = []
    rag_context: dict | None = None


# --- Streaming request models ---


class ResearchQueryRequest(BaseModel):
    question: str
    conversation_id: str | None = None
    case_id: str | None = None
    case_context: dict | None = None


class ResearchFollowUpRequest(BaseModel):
    conversation_id: str
    question: str
    case_context: dict | None = None
