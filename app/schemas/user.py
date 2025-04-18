from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    name: str
    role: str = "user"  # Optional role input (admin, team, founder, etc.)


class TokenPayload(BaseModel):
    sub: str
    tenant_id: str
    role: str


class UserOut(BaseModel):
    user_id: str
    access_token: str
    token_type: str = "bearer"

class MeResponse(BaseModel):
    id: str
    email: EmailStr
    tenant_id: str
    role: str
    name: str | None = None
    is_admin: bool = False
    created_at: str
