from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.db import get_db
from app.dependencies.auth import get_current_user
from app.services.assistant_service import ensure_assistant_for_role
from app.services.sparring_prompt import get_rendered_prompt
from app.stella_sdk.runner import run_assistant
import logging
import re

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    message: str
    sparring_mode: bool = False


# === POST /ideas/{project_id}/chat/{role}
@router.post("/ideas/{project_id}/chat/{role}")
async def chat_with_project_role(
    project_id: UUID,
    role: str,
    body: ChatMessage,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
) -> dict:
    assistant_id = await ensure_assistant_for_role(project_id, role, user, db)

    # Load usage plan
    plan = db.execute(
        text("SELECT p.max_tokens FROM user_plans p JOIN users u ON u.plan_id = p.id WHERE u.id = :user_id"),
        {"user_id": user["id"]}
    ).fetchone()
    if not plan:
        raise HTTPException(status_code=400, detail="User has no plan")

    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = db.execute(
        text("SELECT COALESCE(SUM(tokens_used), 0) FROM token_usage WHERE user_id = :user_id AND created_at >= :start"),
        {"user_id": user["id"], "start": start_of_month}
    ).scalar()

    try:
        # Optional: Inject sparring mode system prompt
        system_prompt = get_rendered_prompt(project_id, role, db) if body.sparring_mode else None

        gpt_reply, thread_id = await run_assistant(
            project_id=project_id,
            role=role,
            message=body.message,
            assistant_id=assistant_id,
            tenant_id=user["tenant_id"],
            user_id=user["id"],
            db=db,
            system_message=system_prompt
        )

        tokens_used = 800  # Estimate (or replace with real tracking if available)

        if used + tokens_used > plan.max_tokens:
            raise HTTPException(status_code=403, detail="Token limit exceeded")

        # Extract viability score if present
        viability_score = None
        match = re.search(r"viability score:?\s*(\d{1,3})", gpt_reply, re.IGNORECASE)
        if match:
            viability_score = int(match.group(1))

        # Store both messages
        db.execute(
            text("""
                INSERT INTO idea_chat_log (id, idea_id, user_id, role, message)
                VALUES 
                    (:id1, :project_id, :user_id, 'user', :msg1),
                    (:id2, :project_id, :user_id, :role, :msg2)
            """),
            {
                "id1": str(uuid4()),
                "id2": str(uuid4()),
                "project_id": str(project_id),
                "user_id": user["id"],
                "msg1": body.message,
                "msg2": gpt_reply,
                "role": role
            }
        )

        # Token usage log
        db.execute(
            text("""
                INSERT INTO token_usage (id, user_id, idea_id, tokens_used, created_at)
                VALUES (:id, :user_id, :idea_id, :tokens_used, NOW())
            """),
            {
                "id": str(uuid4()),
                "user_id": user["id"],
                "idea_id": str(project_id),
                "tokens_used": tokens_used
            }
        )

        # Update score and history if found
        if viability_score is not None:
            db.execute(
                text("""
                    UPDATE ideas SET viability_score = :score, updated_at = NOW()
                    WHERE id = :id AND user_id = :user_id
                """),
                {
                    "score": viability_score,
                    "id": str(project_id),
                    "user_id": user["id"]
                }
            )
            db.execute(
                text("""
                    INSERT INTO viability_score_history (id, idea_id, user_id, score, source, created_at)
                    VALUES (:id, :idea_id, :user_id, :score, :source, NOW())
                """),
                {
                    "id": str(uuid4()),
                    "idea_id": str(project_id),
                    "user_id": user["id"],
                    "score": viability_score,
                    "source": role
                }
            )

        db.commit()

        return {
            "response": gpt_reply,
            "thread_id": thread_id,
            "assistant_id": assistant_id,
            "role": role,
            "project_id": str(project_id),
            "tokens_used": tokens_used,
            "tokens_remaining": plan.max_tokens - used - tokens_used,
            "viability_score": viability_score
        }

    except Exception as e:
        logger.exception(f"[{role.upper()} Assistant] GPT failed")
        raise HTTPException(status_code=500, detail=f"{role.upper()} assistant failed: {str(e)}")


# === GET /ideas/{project_id}/chat-log
@router.get("/ideas/{project_id}/chat-log")
def get_chat_log(
    project_id: UUID,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    plan = db.execute(
        text("""
        SELECT p.max_tokens
        FROM user_plans p
        JOIN users u ON u.plan_id = p.id
        WHERE u.id = :user_id
        """), {"user_id": user["id"]}
    ).fetchone()

    if not plan:
        raise HTTPException(status_code=400, detail="User has no plan")

    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = db.execute(
        text("""
        SELECT COALESCE(SUM(tokens_used), 0)
        FROM token_usage
        WHERE user_id = :user_id AND created_at >= :start
        """),
        {"user_id": user["id"], "start": start_of_month}
    ).scalar()

    rows = db.execute(
        text("""
        SELECT role, message, created_at
        FROM idea_chat_log
        WHERE idea_id = :idea_id AND user_id = :user_id
        ORDER BY created_at ASC
        """),
        {"idea_id": str(project_id), "user_id": user["id"]}
    ).fetchall()

    score = db.execute(
        text("""
        SELECT viability_score
        FROM ideas
        WHERE id = :id AND user_id = :user_id
        """),
        {"id": str(project_id), "user_id": user["id"]}
    ).scalar()

    return {
        "messages": [
            {
                "role": row.role,
                "message": row.message,
                "created_at": row.created_at.isoformat()
            } for row in rows
        ],
        "tokens_used": used,
        "tokens_remaining": plan.max_tokens - used,
        "viability_score": score
    }
