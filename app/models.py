from pydantic import BaseModel, EmailStr

class WaitlistEntry(BaseModel):
    email: EmailStr

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    email: EmailStr
