from fastapi import APIRouter, HTTPException, Request
from app.db import get_db_connection

router = APIRouter()

@router.post("/api/waitlist")
async def add_to_waitlist(request: Request):
    data = await request.json()
    print("Received:", data)

    if "email" not in data:
        raise HTTPException(status_code=400, detail="Missing email")

    try:
        conn = await get_db_connection()
        await conn.execute(
            "INSERT INTO waitlist (email) VALUES ($1)", data["email"]
        )
        await conn.close()
        return {"message": "Email added to waitlist"}
    except Exception as e:
        print("❌ DB error:", e)
        raise HTTPException(status_code=400, detail=str(e))
