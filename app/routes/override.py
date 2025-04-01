import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from databases import Database
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set!")
database = Database(DATABASE_URL)

router = APIRouter(prefix="/api/override", tags=["Override"])

class OverrideRequest(BaseModel):
    tenant_id: str
    decision_type: str  # e.g., "board_meeting", "design_output", "analytics_decision"
    decision_id: str    # ID of the decision to override
    override_message: str

class OverrideResponse(BaseModel):
    id: str
    tenant_id: str
    decision_type: str
    decision_id: str
    override_message: str
    created_at: datetime

@router.post("/", response_model=OverrideResponse)
async def create_override(override: OverrideRequest):
    override_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    query = """
    INSERT INTO overrides (id, tenant_id, decision_type, decision_id, override_message, created_at)
    VALUES (:id, :tenant_id, :decision_type, :decision_id, :override_message, :created_at)
    """
    values = {
        "id": override_id,
        "tenant_id": override.tenant_id,
        "decision_type": override.decision_type,
        "decision_id": override.decision_id,
        "override_message": override.override_message,
        "created_at": created_at,
    }
    try:
        await database.execute(query=query, values=values)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return OverrideResponse(
        id=override_id,
        tenant_id=override.tenant_id,
        decision_type=override.decision_type,
        decision_id=override.decision_id,
        override_message=override.override_message,
        created_at=created_at,
    )
