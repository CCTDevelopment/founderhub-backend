from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from uuid import uuid4
from datetime import datetime, timedelta
from jose import jwt
import bcrypt
import os
from dotenv import load_dotenv
from app.core.db import get_db
from app.dependencies.auth import get_current_user

load_dotenv()

router = APIRouter()

SECRET_KEY = os.getenv("JWT_SECRET", "supersecret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# -----------------------------
# Models
# -----------------------------

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    user_id: str
    access_token: str
    token_type: str = "bearer"

# -----------------------------
# Routes
# -----------------------------

@router.post("/auth/register", response_model=TokenResponse)
async def register_user(payload: UserRegister):
    db = await get_db()
    user_id = str(uuid4())
    tenant_id = str(uuid4())  # You could change this to link to an existing tenant if needed
    hashed_pw = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt()).decode()

    try:
        await db.execute("""
            INSERT INTO users (id, tenant_id, email, hashed_password, is_admin, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, user_id, tenant_id, payload.email.lower(), hashed_pw, False, datetime.utcnow())
    except Exception as e:
        raise HTTPException(status_code=400, detail="Email already registered")

    token = _generate_token(user_id)
    return TokenResponse(user_id=user_id, access_token=token)

@router.post("/auth/login", response_model=TokenResponse)
async def login_user(payload: UserLogin):
    db = await get_db()
    row = await db.fetchrow("SELECT id, hashed_password FROM users WHERE email = $1", payload.email.lower())

    if not row or not bcrypt.checkpw(payload.password.encode("utf-8"), row["hashed_password"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _generate_token(row["id"])
    return TokenResponse(user_id=row["id"], access_token=token)

@router.get("/auth/me")
async def get_me(user=Depends(get_current_user)):
    return {
        "user_id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "created_at": user["created_at"],
    }

# -----------------------------
# Internal Helpers
# -----------------------------

def _generate_token(user_id: str):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
