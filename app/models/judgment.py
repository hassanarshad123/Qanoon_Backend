from pydantic import BaseModel


class JudgmentCreate(BaseModel):
    case_title: str
    case_number: str | None = None
    court: str | None = None
    brief_id: str | None = None
    case_data: dict | None = None
    rag_results: list[dict] = []
    sections: list[dict] = []


class JudgmentStatusUpdate(BaseModel):
    status: str


class JudgmentSectionContentUpdate(BaseModel):
    content: str
    increment_regeneration: bool = False


class JudgmentSectionReviewUpdate(BaseModel):
    status: str
    flag_note: str | None = None


class JudgmentChatMessage(BaseModel):
    role: str
    content: str
    citations: list[dict] = []


# --- Streaming request models ---


class JudgmentGenerateRequest(BaseModel):
    brief_id: str | None = None
    case_title: str
    case_number: str | None = None
    court: str | None = None
    case_data: dict | None = None


class JudgmentChatStreamRequest(BaseModel):
    judgment_context: str = ""
    messages: list[dict] = []
    user_message: str


class JudgmentRegenerateRequest(BaseModel):
    section_title: str
    current_content: str
    judge_note: str
    judgment_context: str = ""
