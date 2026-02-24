from pydantic import BaseModel, field_validator


VALID_ROLES = {"lawyer", "judge", "law_student", "common_person"}


class OnboardingSubmitRequest(BaseModel):
    role: str
    email: str
    data: dict
    user_id: str | None = None

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError("Invalid role")
        return v

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        if not v or "@" not in v:
            raise ValueError("Email is required")
        return v.lower().strip()


class ComingSoonRequest(BaseModel):
    role: str
    email: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError("Invalid role")
        return v

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        if not v or "@" not in v:
            raise ValueError("Email is required")
        return v.lower().strip()
