import logging
from uuid import uuid4
from datetime import datetime
from openai import AsyncOpenAI
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

client = AsyncOpenAI()
logger = logging.getLogger(__name__)

def get_assistant_id(project_id: str, role: str, db: Session) -> str | None:
    row = db.execute(
        text("""
        SELECT assistant_id FROM project_assistants
        WHERE project_id = :project_id AND role = :role
        LIMIT 1
        """),
        {"project_id": project_id, "role": role}
    ).fetchone()
    return row.assistant_id if row else None

def store_assistant_id(project_id: str, role: str, assistant_id: str, db: Session):
    db.execute(
        text("""
        INSERT INTO project_assistants (id, project_id, role, assistant_id, created_at, updated_at)
        VALUES (:id, :project_id, :role, :assistant_id, NOW(), NOW())
        ON CONFLICT (project_id, role) DO UPDATE
        SET assistant_id = EXCLUDED.assistant_id,
            updated_at = NOW()
        """),
        {
            "id": str(uuid4()),
            "project_id": project_id,
            "role": role,
            "assistant_id": assistant_id
        }
    )
    db.commit()

def get_token_limit_and_usage(user, db: Session):
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = db.execute(
        text("""
        SELECT p.max_tokens, COALESCE(SUM(t.tokens_used), 0) as tokens_used
        FROM subscriptions s
        JOIN user_plans p ON s.plan_id = p.id
        LEFT JOIN token_usage t ON s.tenant_id = t.user_id AND t.created_at >= :start
        WHERE s.tenant_id = :tenant_id
        GROUP BY p.max_tokens
        """),
        {"tenant_id": user["tenant_id"], "start": start_of_month}
    ).fetchone()

    if not result:
        return 0, 0

    return result.max_tokens, result.tokens_used

def enforce_token_limit(user, db: Session):
    max_tokens, used_tokens = get_token_limit_and_usage(user, db)
    if max_tokens and used_tokens >= max_tokens:
        raise HTTPException(
            status_code=403,
            detail=f"Token quota exceeded ({used_tokens}/{max_tokens}). Wait until next month to continue."
        )

async def create_dynamic_assistant(project_id: str, role: str, fallback_response: str, db: Session):
    name = f"{project_id} - {role.title()}"
    instructions = f"You are a simulated expert in the role of {role} for project {project_id}. Use your domain expertise to evaluate and guide startup decisions."

    # Save fallback response to file for training context
    file_path = f"/tmp/{project_id}_{role}_training.txt"
    with open(file_path, "w") as f:
        f.write(fallback_response)

    file = await client.files.create(file=open(file_path, "rb"), purpose="assistants")

    assistant = await client.beta.assistants.create(
        name=name,
        instructions=instructions,
        model="gpt-4o"
    )

    # Attach the fallback file to this assistant
    await client.beta.assistants.files.create(
        assistant_id=assistant.id,
        file_id=file.id
    )

    store_assistant_id(project_id, role, assistant.id, db)
    logger.info(f"✅ Created assistant for {project_id} [{role}]: {assistant.id}")
    return assistant.id