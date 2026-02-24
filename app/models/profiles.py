from pydantic import BaseModel


class JudgeProfile(BaseModel):
    id: str
    user_id: str
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    court_level: str | None = None
    designation: str | None = None
    province: str | None = None
    city: str | None = None
    court_name: str | None = None
    tour_completed: bool = False
    created_at: str
    updated_at: str


class JudgeProfileUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    court_level: str | None = None
    designation: str | None = None
    province: str | None = None
    city: str | None = None
    court_name: str | None = None


class LawyerProfile(BaseModel):
    id: str
    user_id: str
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    bar_council_number: str | None = None
    years_of_experience: str | None = None
    practice_areas: list[str] = []
    province: str | None = None
    city: str | None = None
    primary_court: str | None = None
    firm_type: str | None = None
    firm_name: str | None = None
    tour_completed: bool = False
    created_at: str
    updated_at: str


class LawyerProfileUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    bar_council_number: str | None = None
    years_of_experience: str | None = None
    practice_areas: list[str] | None = None
    province: str | None = None
    city: str | None = None
    primary_court: str | None = None
    firm_type: str | None = None
    firm_name: str | None = None


class LawyerTourState(BaseModel):
    """Flexible tour state — extra fields allowed."""
    welcome_shown: bool | None = None
    visited_sections: dict[str, str] | None = None

    model_config = {"extra": "allow"}


class LawyerTourPatch(BaseModel):
    model_config = {"extra": "allow"}


class ChapterCompleteRequest(BaseModel):
    chapter_id: str


class SectionVisitRequest(BaseModel):
    route: str
