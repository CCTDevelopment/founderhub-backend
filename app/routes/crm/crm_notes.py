from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from uuid import uuid4
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.db import get_db
from app.dependencies.auth import get_current_user  # must return user["id"] and user["tenant_id"]

router = APIRouter()

# -----------------------------
# 📦 Pydantic Schemas
# -----------------------------
class NoteCreate(BaseModel):
    content: str

class NoteOut(NoteCreate):
    id: str
    tenant_id: str
    lead_id: str
    created_by: str
    created_at: datetime

# -----------------------------
# 📥 Add Note to a Lead
# -----------------------------
@router.post("/crm/leads/{lead_id}/notes", response_model=NoteOut)
def add_note_to_lead(
    lead_id: str,
    note: NoteCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    note_id = str(uuid4())
    created_at = datetime.utcnow()

    try:
        db.execute(
            text("""
                INSERT INTO crm_lead_notes (
                    id, tenant_id, lead_id, created_by, content, created_at
                ) VALUES (
                    :id, :tenant_id, :lead_id, :created_by, :content, :created_at
                )
            """),
            {
                "id": note_id,
                "tenant_id": user["tenant_id"],
                "lead_id": lead_id,
                "created_by": user["id"],
                "content": note.content,
                "created_at": created_at,
            }
        )
        db.commit()

        return {
            "id": note_id,
            "tenant_id": user["tenant_id"],
            "lead_id": lead_id,
            "created_by": user["id"],
            "content": note.content,
            "created_at": created_at
        }

    except Exception as e:
        db.rollback()
        print("❌ Error saving note:", e)
        raise HTTPException(status_code=500, detail="Failed to save note")

# -----------------------------
# 📤 Get Notes for a Lead
# -----------------------------
@router.get("/crm/leads/{lead_id}/notes", response_model=List[NoteOut])
def get_notes_for_lead(
    lead_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        rows = db.execute(
            text("""
                SELECT * FROM crm_lead_notes
                WHERE lead_id = :lead_id AND tenant_id = :tenant_id
                ORDER BY created_at ASC
            """),
            {
                "lead_id": lead_id,
                "tenant_id": user["tenant_id"]
            }
        ).mappings().all()

        return rows

    except Exception as e:
        print("❌ Error fetching notes:", e)
        raise HTTPException(status_code=500, detail="Failed to load notes")
