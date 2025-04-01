# Pydantic Models (app/schemas/user.py)
from pydantic import BaseModel, EmailStr, Field

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    name: str

class UserOut(BaseModel):
    user_id: str
    access_token: str
    token_type: str = "bearer"
