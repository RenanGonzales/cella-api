import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.security import BCRYPT_MAX_BYTES

PASSWORD_MIN_LENGTH = 8


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class RegisterRequest(BaseModel):
    """Sign up and, in the same step, create a household or join one with an invite code."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH)
    household_name: str | None = Field(default=None, min_length=1, max_length=100)
    invite_code: str | None = Field(default=None, min_length=1, max_length=20)

    _normalize = field_validator("email")(_normalize_email)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, password: str) -> str:
        if len(password.encode()) > BCRYPT_MAX_BYTES:
            raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes")
        return password

    @model_validator(mode="after")
    def exactly_one_household_option(self) -> "RegisterRequest":
        if (self.household_name is None) == (self.invite_code is None):
            raise ValueError("Send either household_name (create) or invite_code (join)")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    _normalize = field_validator("email")(_normalize_email)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")


class DemoPartner(BaseModel):
    """The second person of the demo household, to show two phones side by side."""

    id: uuid.UUID
    name: str
    access_token: str


class DemoSessionResponse(TokenResponse):
    """Token of the first demo person (Alex) plus the second one (Sam)."""

    partner: DemoPartner


class MemberOut(BaseModel):
    id: uuid.UUID
    name: str


class HouseholdOut(BaseModel):
    id: uuid.UUID
    name: str
    invite_code: str
    members: list[MemberOut]


class FeaturesOut(BaseModel):
    """What this account may use, so the app only shows what works."""

    receipt_ai: bool
    is_demo: bool


class MeResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    household: HouseholdOut
    features: FeaturesOut
