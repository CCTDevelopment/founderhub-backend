import os
import uuid
import logging
from datetime import datetime
from typing import List, Optional

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv

# === Load env
load_dotenv()

# === Router
router = APIRouter()
logger = logging.getLogger("validation_signals")
logging.basicConfig(level=logging.INFO)

# === DB Connection
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

# === Models
class SignalCreate(BaseModel):
    tenant_id: str
    project_id: str
    contact_id: Optional[str]
    type: str                   # e.g. demo_requested, objection, feedback, etc.
    note: Optional[str]
    strength: Optional[int] = 3
    created_by: Optional[str]

class SignalOut(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    contact_id: Optional[str]
    type: str
    note: Optional[str]
    strength: int
    created_by: Optional[str]
    created_at: datetime

# === Routes

@router.post("/projects/{project_id}/signals", response_model=SignalOut)
async def add_validation_signal(project_id: str, signal: SignalCreate):
    signal_id = str(uuid.uuid4())
    created_at = datetime.utcnow()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO validation_signals (
                        id, tenant_id, project_id, contact_id, type, note, strength, created_by, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    signal_id,
                    signal.tenant_id,
                    project_id,
                    signal.contact_id,
                    signal.type,
                    signal.note,
                    signal.strength,
                    signal.created_by,
                    created_at
                ))
            conn.commit()
    except Exception:
        logger.exception("Error inserting validation signal")
        raise HTTPException(status_code=500, detail="Database error")

    return SignalOut(
        id=signal_id,
        tenant_id=signal.tenant_id,
        project_id=project_id,
        contact_id=signal.contact_id,
        type=signal.type,
        note=signal.note,
        strength=signal.strength,
        created_by=signal.created_by,
        created_at=created_at
    )

@router.get("/projects/{project_id}/signals", response_model=List[SignalOut])
async def get_signals_for_project(
    project_id: str,
    tenant_id: str = Query(...),
    limit: int = Query(100, le=500),
    offset: int = Query(0)
):
    signals = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, tenant_id, project_id, contact_id, type, note, strength, created_by, created_at
                    FROM validation_signals
                    WHERE project_id = %s AND tenant_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (project_id, tenant_id, limit, offset))
                for row in cur.fetchall():
                    signals.append(SignalOut(
                        id=row[0],
                        tenant_id=row[1],
                        project_id=row[2],
                        contact_id=row[3],
                        type=row[4],
                        note=row[5],
                        strength=row[6],
                        created_by=row[7],
                        created_at=row[8]
                    ))
    except Exception:
        logger.exception("Failed to fetch validation signals")
        raise HTTPException(status_code=500, detail="Database error")

    return signals
