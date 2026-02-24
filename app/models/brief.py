from pydantic import BaseModel


class BriefCreate(BaseModel):
    case_title: str
    case_number: str | None = None
    court: str | None = None
    extracted_data: dict | None = None
    uploaded_documents: list[dict] = []
    rag_results: list[dict] = []
    sections: list[dict] = []


class BriefStatusUpdate(BaseModel):
    status: str


class SectionReviewUpdate(BaseModel):
    status: str
    flag_note: str | None = None


class SectionContentUpdate(BaseModel):
    content: str
    increment_regeneration: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str
    citations: list[dict] = []


# --- Streaming request models ---


class BriefGenerateRequest(BaseModel):
    extracted_data: dict
    rag_results: list[dict] = []


class BriefChatStreamRequest(BaseModel):
    brief_context: str = ""
    messages: list[dict] = []
    user_message: str


class BriefRegenerateRequest(BaseModel):
    section_title: str
    current_content: str
    judge_note: str
    brief_context: str = ""


class BriefAnalyzeRequest(BaseModel):
    documents: list[dict]


class BriefAnalyzeChunkRequest(BaseModel):
    documents: list[dict]
    chunk_index: int | None = None
    total_chunks: int | None = None


class BriefPrecedentsRequest(BaseModel):
    extracted_data: dict
