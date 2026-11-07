import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Plain str, not EmailStr: `email-validator` isn't an existing dependency
    # and this field is only ever matched against `users.email` in the DB —
    # format validation at this boundary adds no real safety here.
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}
