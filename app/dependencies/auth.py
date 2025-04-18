from fastapi import Depends, HTTPException, Header
from jose import jwt, JWTError
from app.core.db import get_db
from app.models.user import User
from sqlalchemy.orm import Session
import os
import logging

# === Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# === Config
SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"

if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET environment variable is not set!")

# === Auth Dependency
async def get_current_user(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    if not authorization.startswith("Bearer "):
        logger.warning("⚠️ Missing 'Bearer' in token header.")
        raise HTTPException(status_code=401, detail="Invalid token format")

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if not user_id:
            logger.warning("⚠️ JWT missing 'sub' claim.")
            raise HTTPException(status_code=401, detail="Token missing subject")

        logger.info(f"✅ Decoded token for user: {user_id}")

    except JWTError as e:
        logger.warning(f"⚠️ JWT decode failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Fetch user
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        logger.warning(f"❌ User not found for ID: {user_id}")
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": str(user.id),
        "tenant_id": str(user.tenant_id),
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "is_admin": user.is_admin,
        "created_at": user.created_at
    }
