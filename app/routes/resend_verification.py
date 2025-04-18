from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from uuid import uuid4
import os
from jose import jwt, JWTError

from app.core.db import get_db
from app.models.user import User
from app.models.verification import EmailVerification
from app.services.email import send_verification_email

router = APIRouter()

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"
EXPIRATION_HOURS = int(os.getenv("EMAIL_TOKEN_EXPIRES", 24))

if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET not set")

@router.post("/auth/resend-verification")
def resend_verification(email: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email.lower()).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    record = db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.verified == False
    ).order_by(EmailVerification.created_at.desc()).first()

    now = datetime.utcnow()

    if record and record.expires_at > now:
        # ✅ Token still valid, resend same one
        token = record.token
    else:
        # 🔄 Generate a new one
        token = jwt.encode({
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(hours=EXPIRATION_HOURS)
        }, SECRET_KEY, algorithm=ALGORITHM)

        new_record = EmailVerification(
            id=str(uuid4()),
            user_id=user.id,
            email=user.email,
            token=token,
            expires_at=now + timedelta(hours=EXPIRATION_HOURS),
            verified=False
        )
        db.add(new_record)
        db.commit()

    # 📬 Resend email
    try:
        send_verification_email(user.email, user.name, token, str(user.id), db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email send failed: {str(e)}")

    return {"message": "✅ Verification email sent."}
