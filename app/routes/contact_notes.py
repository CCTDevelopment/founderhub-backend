import os
import uuid
import logging
from datetime import datetime
from typing import List, Optional

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv

# === Load environment variables
load_dotenv()

# === Logger
logger = logging.getLogger("contact_notes")
logging.basicConfig(level=logging.INFO)

# === FastAPI router
router = APIRouter()

# === Database connection
def get_db_connection():
    try:
        return psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT", 5432)
        )
    except Exception as e:
        logger.exception("Could not connect to the database")
        raise HTTPException(status_code=500, detail="Database connection failed")

# === Pydantic Models
class NoteCreate(BaseModel):
    tenant_id: str
    contact_id: str
    note: str
    created_by: Optional[str] = None  # Optional: Track the author of the note
    source: Optional[str] = "manual"  # e.g., webhook, email, manual
    channel: Optional[str] = "internal"  # e.g., email, call, Slack

class NoteOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    note: str
    created_by: Optional[str]
    source: Optional[str]
    channel: Optional[str]
    created_at: datetime

# === Routes

@router.post("/contacts/{contact_id}/notes", response_model=NoteOut)
async def add_contact_note(contact_id: str, note: NoteCreate):
    note_id = str(uuid.uuid4())
    created_at = datetime.utcnow()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO contact_notes (
                        id, tenant_id, contact_id, note, created_by, source, channel, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    note_id,
                    note.tenant_id,
                    contact_id,
                    note.note,
                    note.created_by,
                    note.source,
                    note.channel,
                    created_at
                ))
            conn.commit()
    except Exception as e:
        logger.exception("Failed to insert contact note")
        raise HTTPException(status_code=500, detail="Database error")

    return NoteOut(
        id=note_id,
        tenant_id=note.tenant_id,
        contact_id=contact_id,
        note=note.note,
        created_by=note.created_by,
        source=note.source,
        channel=note.channel,
        created_at=created_at
    )

@router.get("/contacts/{contact_id}/notes", response_model=List[NoteOut])
async def get_contact_notes(
    contact_id: str,
    tenant_id: str = Query(...),
    limit: int = Query(100, le=500),
    offset: int = Query(0)
):
    notes = []

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, tenant_id, contact_id, note, created_by, source, channel, created_at
                    FROM contact_notes
                    WHERE contact_id = %s AND tenant_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s OFFSET %s
                """, (contact_id, tenant_id, limit, offset))

                rows = cur.fetchall()
                for row in rows:
                    notes.append(NoteOut(
                        id=row[0],
                        tenant_id=row[1],
                        contact_id=row[2],
                        note=row[3],
                        created_by=row[4],
                        source=row[5],
                        channel=row[6],
                        created_at=row[7],
                    ))
    except Exception:
        logger.exception("Failed to fetch contact notes")
        raise HTTPException(status_code=500, detail="Database error")

    return notes

@router.delete("/contacts/{contact_id}/notes/{note_id}")
async def delete_contact_note(contact_id: str, note_id: str, tenant_id: str = Query(...)):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM contact_notes
                    WHERE id = %s AND contact_id = %s AND tenant_id = %s
                """, (note_id, contact_id, tenant_id))
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Note not found")
            conn.commit()
    except Exception:
        logger.exception("Failed to delete contact note")
        raise HTTPException(status_code=500, detail="Database error")

    return {"detail": "Note deleted successfully"}
