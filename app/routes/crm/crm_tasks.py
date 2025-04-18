from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
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
class TaskCreate(BaseModel):
    title: str
    due_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = ""

class TaskOut(TaskCreate):
    id: str
    tenant_id: str
    lead_id: str
    created_by: str
    completed: bool
    created_at: datetime
    completed_at: Optional[datetime] = None

# -----------------------------
# 📥 Add Task to a Lead
# -----------------------------
@router.post("/crm/leads/{lead_id}/tasks", response_model=TaskOut)
def add_task_to_lead(
    lead_id: str,
    task: TaskCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task_id = str(uuid4())
    created_at = datetime.utcnow()

    try:
        db.execute(
            text("""
                INSERT INTO crm_lead_tasks (
                    id, tenant_id, lead_id, title, due_date, notes,
                    assigned_to, created_by, completed, created_at
                ) VALUES (
                    :id, :tenant_id, :lead_id, :title, :due_date, :notes,
                    :assigned_to, :created_by, :completed, :created_at
                )
            """),
            {
                "id": task_id,
                "tenant_id": user["tenant_id"],
                "lead_id": lead_id,
                "title": task.title,
                "due_date": task.due_date,
                "notes": task.notes,
                "assigned_to": task.assigned_to,
                "created_by": user["id"],
                "completed": False,
                "created_at": created_at
            }
        )
        db.commit()

        return {
            **task.dict(),
            "id": task_id,
            "tenant_id": user["tenant_id"],
            "lead_id": lead_id,
            "created_by": user["id"],
            "completed": False,
            "created_at": created_at,
            "completed_at": None
        }

    except Exception as e:
        db.rollback()
        print("❌ Error adding task:", e)
        raise HTTPException(status_code=500, detail="Failed to save task")

# -----------------------------
# 📤 Get Tasks for a Lead
# -----------------------------
@router.get("/crm/leads/{lead_id}/tasks", response_model=List[TaskOut])
def get_tasks_for_lead(
    lead_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        rows = db.execute(
            text("""
                SELECT * FROM crm_lead_tasks
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
        print("❌ Error fetching tasks:", e)
        raise HTTPException(status_code=500, detail="Failed to load tasks")

# -----------------------------
# ✅ Mark Task Complete
# -----------------------------
@router.post("/crm/tasks/{task_id}/complete")
def mark_task_complete(
    task_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    completed_at = datetime.utcnow()

    try:
        db.execute(
            text("""
                UPDATE crm_lead_tasks
                SET completed = TRUE, completed_at = :completed_at
                WHERE id = :task_id AND tenant_id = :tenant_id
            """),
            {
                "task_id": task_id,
                "tenant_id": user["tenant_id"],
                "completed_at": completed_at
            }
        )
        db.commit()

        return {"status": "ok", "task_id": task_id}

    except Exception as e:
        db.rollback()
        print("❌ Error completing task:", e)
        raise HTTPException(status_code=500, detail="Failed to complete task")
