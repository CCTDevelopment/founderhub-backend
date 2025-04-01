from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from uuid import UUID, uuid4
from datetime import datetime
from app.core.db import get_db
from app.dependencies.auth import get_current_user
from openai import AsyncOpenAI
import os
import traceback

router = APIRouter()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class ChatMessage(BaseModel):
    message: str

class ChatEntry(BaseModel):
    role: str  # 'user' or 'assistant'
    message: str
    created_at: datetime

@router.get("/ideas/{id}/chat-log", response_model=list[ChatEntry])
async def get_chat_log(id: UUID, user=Depends(get_current_user)):
    db = await get_db()
    rows = await db.fetch("""
        SELECT role, message, created_at
        FROM idea_chat_log
        WHERE idea_id = $1 AND user_id = $2
        ORDER BY created_at ASC
    """, str(id), user["id"])

    return [dict(row) for row in rows]

@router.post("/ideas/{id}/chat")
async def chat_with_gpt(id: UUID, body: ChatMessage, user=Depends(get_current_user)):
    db = await get_db()

    # 🗂️ Fetch chat history
    history = await db.fetch("""
        SELECT role, message FROM idea_chat_log
        WHERE idea_id = $1 AND user_id = $2
        ORDER BY created_at ASC
        LIMIT 10
    """, str(id), user["id"])

    # 🧠 GPT prompt upgrade
    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI co-founder with deep startup insight. "
                "Your job is not to affirm or praise — your job is to push the founder toward sharper thinking.\n\n"
                "In every message:\n"
                "1. Question their assumptions — what are they betting on that may not be true?\n"
                "2. Identify risks — what might break, go wrong, or fail to resonate?\n"
                "3. Offer reframes — suggest new angles, use cases, or go-to-market pivots\n"
                "4. Help improve — provide sharper ways to explain, test, or build the idea\n"
                "5. Finish with one clear question to move them forward\n\n"
                "Be direct. Be strategic. No fluff. Your job is to make the idea better or kill it fast.\n"
            )
        }
    ] + [
        {"role": row["role"], "content": row["message"]} for row in history
    ] + [
        {"role": "user", "content": body.message}
    ]

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=700
        )

        gpt_reply = response.choices[0].message.content.strip()

        await db.execute("""
            INSERT INTO idea_chat_log (id, idea_id, user_id, role, message)
            VALUES ($1, $2, $3, 'user', $4),
                   ($5, $2, $3, 'assistant', $6)
        """, str(uuid4()), str(id), user["id"], body.message, str(uuid4()), gpt_reply)

        return {"response": gpt_reply}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="GPT chat failed")
