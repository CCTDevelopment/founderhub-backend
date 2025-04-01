from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from uuid import uuid4
import bcrypt
import os
import logging

from app.core.db import get_db  # Your production database dependency
from app.models.user import User  # Your SQLAlchemy user model

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Use OAuth2 scheme to extract the token from the Authorization header.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

# In production, the secret should be stored securely (e.g. in a secrets manager or secure DB table).
SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET environment variable is not set!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Pydantic models for tokens
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    sub: str | None = None
    tenant_id: str | None = None
    role: str | None = None

# Helper functions for password hashing and verification.
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()

# Authenticate user credentials against the database.
def authenticate_user(db, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        logger.warning("Authentication failed: User not found for email %s", email)
        return None
    if not verify_password(password, user.hashed_password):
        logger.warning("Authentication failed: Incorrect password for user %s", email)
        return None
    return user

# JWT token generation helper.
def _generate_token(user_id: str, tenant_id: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": datetime.utcnow(),
        "exp": expire
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token

@router.post("/token", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db = Depends(get_db)
):
    """
    Issues a JWT token after validating user credentials.
    The token payload contains user ID, tenant ID, and role.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    access_token = _generate_token(user.id, user.tenant_id, user.role)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users/me")
def read_users_me(current_user: dict = Depends(oauth2_scheme)):
    """
    Retrieves current user information based on the provided JWT token.
    In production, this should return data from a secure lookup (e.g., your user model).
    """
    # Here, we assume that get_current_user is implemented in a production‑ready way in your app.
    user = current_user  # In production, decode and return secure user info.
    return user

@router.get("/auth/me")
async def get_me(user=Depends(lambda: get_current_user())):
    """
    Returns user details.
    Replace this dependency with your production‑ready get_current_user implementation.
    """
    return {
        "user_id": user["id"],
        "tenant_id": user["tenant_id"],
        "role": user["role"],
        "email": user.get("email"),
        "name": user.get("name"),
        "created_at": user.get("created_at"),
    }
