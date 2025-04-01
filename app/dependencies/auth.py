from fastapi import Depends, HTTPException, Header
from jose import jwt, JWTError
from app.core.db import get_db
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET", "supersecret")
ALGORITHM = "HS256"

async def get_current_user(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing subject")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    db = await get_db()
    user = await db.fetchrow("""
        SELECT id, tenant_id, email, name, is_admin, created_at
        FROM users
        WHERE id = $1
    """, user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return dict(user)
