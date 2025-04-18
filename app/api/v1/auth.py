import os
import logging
from uuid import uuid4
from datetime import datetime, timedelta
from fastapi import Request, APIRouter, Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import bcrypt
import traceback

from app.core.db import get_db
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.models.verification import EmailVerification
from app.services.email import send_verification_email, send_template_email
from app.services.security import log_login_event

# === CONFIG ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

if not SECRET_KEY:
    raise RuntimeError("Missing JWT_SECRET in environment")

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

# === Pydantic Models ===
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "user"

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

# === Hashing Utilities ===
def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

# === Token Utilities ===
def create_jwt_token(data: dict, expires_in_minutes: int):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=expires_in_minutes)
    payload["iat"] = datetime.utcnow()
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

def create_access_token(user: User) -> str:
    return create_jwt_token({
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": user.role
    }, ACCESS_TOKEN_EXPIRE_MINUTES)

def create_refresh_token(user: User) -> str:
    return create_jwt_token({
        "sub": str(user.id),
        "token_type": "refresh"
    }, REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60)

# === Token Issuer ===
def issue_tokens(user: User, db: Session):
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked == False
    ).delete()

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)

    db.add(RefreshToken(
        id=str(uuid4()),
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        revoked=False
    ))
    db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

# === Auth Logic ===
def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

# === Register ===
@router.post("/auth/register", response_model=TokenResponse)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid4())
    tenant_id = str(uuid4())

    user = User(
        id=user_id,
        email=payload.email.lower(),
        hashed_password=get_password_hash(payload.password),
        name=payload.name,
        tenant_id=tenant_id,
        role=payload.role.lower(),
        is_admin=payload.role.lower() == "admin",
        created_at=datetime.utcnow()
    )
    db.add(user)

    token = create_jwt_token(
        {"sub": user_id}, expires_in_minutes=24 * 60
    )

    verification = EmailVerification(
        id=str(uuid4()),
        user_id=user_id,
        email=user.email,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        verified=False,
        created_at=datetime.utcnow()
    )
    db.add(verification)
    db.commit()

    send_verification_email(user.email, user.name, token, str(user.id), db)
    return issue_tokens(user, db)

# === Login ===
@router.post("/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    is_verified = db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.verified == True
    ).first()

    if not is_verified:
        token = create_jwt_token({"sub": str(user.id)}, expires_in_minutes=24 * 60)

        record = db.query(EmailVerification).filter(
            EmailVerification.user_id == user.id
        ).first()

        if record:
            logger.info("🔁 Updating existing verification token")
            record.token = token
            record.expires_at = datetime.utcnow() + timedelta(hours=24)
            record.verified = False
        else:
            logger.info("✨ Creating new email verification record")
            record = EmailVerification(
                id=str(uuid4()),
                user_id=user.id,
                email=user.email,
                token=token,
                expires_at=datetime.utcnow() + timedelta(hours=24),
                verified=False,
                created_at=datetime.utcnow()
            )
            db.add(record)

        db.commit()
        send_verification_email(user.email, user.name, token, str(user.id), db)

        raise HTTPException(
            status_code=403,
            detail="Account not verified. A new verification email has been sent."
        )

    ip = request.client.host or "unknown"
    user_agent = request.headers.get("user-agent", "Unknown")

    try:
        log_login_event(user, ip, user_agent, db)
    except Exception as e:
        raise HTTPException(status_code=403, detail=str(e))

    return issue_tokens(user, db)

# === Refresh ===
@router.post("/auth/refresh", response_model=TokenResponse)
def refresh_token(request: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(request.refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    record = db.query(RefreshToken).filter(
        RefreshToken.token == request.refresh_token,
        RefreshToken.revoked == False,
        RefreshToken.expires_at > datetime.utcnow()
    ).first()

    if not record:
        raise HTTPException(status_code=403, detail="Refresh token revoked or expired")

    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    record.revoked = True
    db.commit()

    return issue_tokens(user, db)

# === Logout ===
@router.post("/auth/logout")
def logout(request: RefreshRequest, db: Session = Depends(get_db)):
    record = db.query(RefreshToken).filter(RefreshToken.token == request.refresh_token).first()
    if record:
        record.revoked = True
        db.commit()
    return {"detail": "Logged out successfully"}

# === /auth/me ===
@router.get("/auth/me")
def get_me(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    try:
        payload = decode_token(authorization.split(" ")[1])
        return {
            "user_id": payload.get("sub"),
            "tenant_id": payload.get("tenant_id"),
            "role": payload.get("role"),
            "exp": payload.get("exp")
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# === Email Verification ===
@router.get("/auth/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    logger.info(f"🔍 Incoming verification token: {token}")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        record = db.query(EmailVerification).filter(
            EmailVerification.token == token,
            EmailVerification.verified == False
        ).first()

        if not record:
            raise HTTPException(status_code=404, detail="Invalid or expired token")

        if not record.expires_at or record.expires_at < datetime.utcnow():
            raise HTTPException(status_code=410, detail="Token expired")

        record.verified = True
        db.commit()

        logger.info(f"✅ Email verified for user: {user_id}")
        return {"message": "✅ Email verified!"}

    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid verification token")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Server error during verification")

# === Resend Verification ===
@router.post("/auth/resend-verification")
def resend_verification(email: EmailStr, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    record = db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.verified == False
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="User already verified")

    token = create_jwt_token({"sub": str(user.id)}, expires_in_minutes=24 * 60)
    record.token = token
    record.expires_at = datetime.utcnow() + timedelta(hours=24)
    db.commit()

    send_verification_email(user.email, user.name, token, str(user.id), db)
    return {"detail": "Verification email resent"}

# === Forgot Password ===
@router.post("/auth/forgot-password")
def forgot_password(email: EmailStr, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email not registered")

    token = create_jwt_token({
        "sub": str(user.id),
        "action": "reset_password"
    }, expires_in_minutes=24 * 60)

    send_template_email(
        to_email=user.email,
        name=user.name,
        template_key="reset_password_link",
        db=db,
        user_id=user.id,
        variables={
            "name": user.name,
            "reset_link": f"https://portal.founderhub.ai/reset-password?token={token}"
        }
    )

    return {"detail": "Password reset link sent."}

# === Change Password ===
@router.post("/auth/change-password")
def change_password(body: ChangePasswordRequest, authorization: str = Header(...), db: Session = Depends(get_db)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload = decode_token(authorization.split(" ")[1])
        user = db.query(User).filter(User.id == payload["sub"]).first()

        if not verify_password(body.current_password, user.hashed_password):
            raise HTTPException(status_code=403, detail="Incorrect current password")

        user.hashed_password = get_password_hash(body.new_password)
        db.commit()
        return {"detail": "Password updated successfully"}
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalid or expired")

# === Reset Password ===
@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.token)

        if payload.get("action") != "reset_password":
            raise HTTPException(status_code=400, detail="Invalid token")

        user = db.query(User).filter(User.id == payload["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.hashed_password = get_password_hash(body.new_password)
        db.commit()

        return {"detail": "Password reset successful"}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
