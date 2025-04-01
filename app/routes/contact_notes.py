import os
import uuid
from datetime import datetime
from typing import List

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

class NoteCreate(BaseModel):
    tenant_id: str
    contact_id: str
    note: str

class NoteOut(BaseModel):
    id: str
    tenant_id: str
    contact_id: str
    note: str
    created_at: datetime

@router.post("/contacts/{contact_id}/notes", response_model=NoteOut)
async def add_contact_note(contact_id: str, note: NoteCreate):
    conn = get_db_connection()
    note_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contact_notes (id, tenant_id, contact_id, note, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (note_id, note.tenant_id, contact_id, note.note, created_at)
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    return NoteOut(id=note_id, tenant_id=note.tenant_id, contact_id=contact_id, note=note.note, created_at=created_at)

@router.get("/contacts/{contact_id}/notes", response_model=List[NoteOut])
async def get_contact_notes(contact_id: str, tenant_id: str = Query(...)):
    conn = get_db_connection()
    notes = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tenant_id, contact_id, note, created_at
                FROM contact_notes
                WHERE contact_id = %s AND tenant_id = %s
                ORDER BY created_at ASC
                """,
                (contact_id, tenant_id)
            )
            rows = cur.fetchall()
            for row in rows:
                notes.append(
                    NoteOut(
                        id=row[0],
                        tenant_id=row[1],
                        contact_id=row[2],
                        note=row[3],
                        created_at=row[4]
                    )
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    return notes
