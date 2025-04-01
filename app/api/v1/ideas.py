from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from uuid import uuid4, UUID
from datetime import datetime
from typing import List, Optional
import os
import logging
from dotenv import load_dotenv
from openai import AsyncOpenAI
import traceback

from app.core.db import get_db
from app.dependencies.auth import get_current_user

# Load environment variables (ideally done once at the application entry point)
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Ensure the OpenAI API key is set
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set!")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)
logger.info("OpenAI API Key loaded successfully.")

router = APIRouter()

# -----------------------------
# Models
# -----------------------------

class IdeaCreate(BaseModel):
    title: str
    problem: str
    audience: str
    solution: str
    notes: str

class IdeaUpdate(IdeaCreate):
    pass

class IdeaOut(IdeaCreate):
    id: str
    vetting_status: str
    vetting_response: Optional[str]
    created_at: datetime
    updated_at: datetime

# -----------------------------
# POST /ideas
# -----------------------------

@router.post("/ideas", response_model=IdeaOut, status_code=status.HTTP_201_CREATED)
async def create_idea(payload: IdeaCreate, user=Depends(get_current_user)):
    db = await get_db()
    idea_id = str(uuid4())
    now = datetime.utcnow()

    try:
        await db.execute(
            """
            INSERT INTO ideas (
                id, tenant_id, user_id,
                title, problem, audience, solution, notes,
                vetting_status, vetting_response, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'pending', NULL, $9, $10)
            """,
            idea_id, user["tenant_id"], user["id"],
            payload.title, payload.problem, payload.audience,
            payload.solution, payload.notes, now, now
        )
    except Exception as e:
        logger.exception("Failed to save idea.")
        raise HTTPException(status_code=500, detail="Failed to save idea")

    return IdeaOut(
        id=idea_id,
        vetting_status="pending",
        vetting_response=None,
        created_at=now,
        updated_at=now,
        **payload.dict()
    )

# -----------------------------
# GET /ideas
# -----------------------------

@router.get("/ideas", response_model=List[IdeaOut])
async def get_user_ideas(user=Depends(get_current_user)):
    db = await get_db()
    try:
        rows = await db.fetch(
            """
            SELECT id, title, problem, audience, solution, notes,
                   vetting_status, vetting_response, created_at, updated_at
            FROM ideas
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user["id"]
        )
        return [
            {
                "id": str(row["id"]),
                "title": row["title"],
                "problem": row["problem"],
                "audience": row["audience"],
                "solution": row["solution"],
                "notes": row["notes"],
                "vetting_status": row["vetting_status"],
                "vetting_response": row["vetting_response"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    except Exception as e:
        logger.exception("Failed to fetch ideas.")
        raise HTTPException(status_code=500, detail=f"Failed to fetch ideas: {str(e)}")

# -----------------------------
# GET /ideas/{id}
# -----------------------------

@router.get("/ideas/{id}")
async def get_idea_by_id(id: UUID, user=Depends(get_current_user)):
    db = await get_db()
    idea = await db.fetchrow(
        """
        SELECT id, title, problem, audience, solution, notes, vetting_status,
               vetting_response, created_at, updated_at
        FROM ideas
        WHERE id = $1 AND user_id = $2
        """,
        str(id), user["id"]
    )

    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    # Convert UUID types to strings if needed.
    return {k: (str(v) if isinstance(v, UUID) else v) for k, v in dict(idea).items()}

# -----------------------------
# PUT /ideas/{id}
# -----------------------------

@router.put("/ideas/{id}")
async def update_idea(id: UUID, payload: IdeaUpdate, user=Depends(get_current_user)):
    db = await get_db()

    result = await db.execute(
        """
        UPDATE ideas
        SET title = $1,
            problem = $2,
            audience = $3,
            solution = $4,
            notes = $5,
            updated_at = NOW()
        WHERE id = $6 AND user_id = $7
        """,
        payload.title, payload.problem, payload.audience,
        payload.solution, payload.notes, str(id), user["id"]
    )

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Idea not found or unauthorized")

    return {"status": "ok"}

# -----------------------------
# POST /ideas/{id}/analyze
# -----------------------------

@router.post("/ideas/{id}/analyze")
async def analyze_idea(id: UUID, user=Depends(get_current_user)):
    db = await get_db()

    idea = await db.fetchrow(
        """
        SELECT title, problem, audience, solution, notes
        FROM ideas
        WHERE id = $1 AND user_id = $2
        """,
        str(id), user["id"]
    )

    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    # Build prompt for GPT analysis
    prompt = f"""
You are an intellectual sparring partner for a startup founder. Your job is not to affirm or praise. Your job is to challenge.

Every time you are given a startup idea, apply the following thinking framework:

1. Analyze Assumptions — What is the founder taking for granted that might not be true?
2. Provide Counterpoints — What would a well-informed skeptic say in response?
3. Test the Logic — Does their reasoning hold up under scrutiny, or are there gaps or flaws?
4. Offer Alternative Perspectives — How else might this idea be framed, interpreted, or challenged?
5. Prioritize Truth Over Agreement — If the idea is weak, say so clearly and explain why.

Maintain a constructive but rigorous tone. You are not here to argue for argument’s sake — you are here to push the founder toward sharper clarity, stronger thinking, and intellectual honesty.

Call out confirmation bias. Challenge assumptions. Highlight risk. Push for truth.

NEVER sugarcoat. NEVER say "great idea" unless it truly withstands the 5-question gauntlet above.

Return your feedback in this format:

---

Verdict: Yes / No / Maybe

Rationale:
- Bullet points explaining your reasoning

Risks:
- Blind spots, assumptions, or things likely to go wrong

Counterpoints:
- What a smart critic would say

Alternative Frames:
- Different ways this idea could be positioned or executed

Next Step:
- What the founder should do next

Viability Score: (0–100)

---

Idea:
Title: {idea['title']}
Problem: {idea['problem']}
Audience: {idea['audience']}
Solution: {idea['solution']}
Notes: {idea['notes']}
"""

    try:
        logger.info("Sending idea analysis to GPT-4o...")
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a startup vetting expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=600
        )
        result = response.choices[0].message.content
        logger.info("Received GPT response (first 120 chars): %s", result[:120])

        await db.execute(
            """
            UPDATE ideas
            SET vetting_response = $1,
                vetting_status = 'analyzed',
                updated_at = NOW()
            WHERE id = $2 AND user_id = $3
            """,
            result, str(id), user["id"]
        )

        return {
            "vetting_response": result,
            "vetting_status": "analyzed"
        }
    except Exception as e:
        logger.exception("GPT analysis failed")
        raise HTTPException(status_code=500, detail=f"GPT failed: {str(e)}")

# -----------------------------
# PUT /ideas/{id}/commit
# -----------------------------

@router.put("/ideas/{id}/commit")
async def commit_idea(id: UUID, user=Depends(get_current_user)):
    db = await get_db()
    result = await db.execute(
        """
        UPDATE ideas
        SET vetting_status = 'committed',
            updated_at = NOW()
        WHERE id = $1 AND user_id = $2
        """,
        str(id), user["id"]
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Idea not found or unauthorized")
    return {"status": "committed"}
