from pydantic import BaseModel, EmailStr

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserOut(BaseModel):
    user_id: str
    access_token: str
    token_type: str = "bearer"
