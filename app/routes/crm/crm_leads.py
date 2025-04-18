from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from uuid import uuid4, UUID
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.dependencies.auth import get_current_user

router = APIRouter()

# -----------------------------
# 📦 Lead Schemas
# -----------------------------
class LeadCreate(BaseModel):
    name: str
    email: EmailStr
    company: str = ""
    phone: str = ""
    stage: str = "New"
    score: str = ""
    rep: str = ""
    tags: str = ""
    notes: str = ""

    class Config:
        extra = "forbid"

class LeadOut(LeadCreate):
    id: UUID
    tenant_id: UUID
    created_at: datetime

# -----------------------------
# 📦 Task Schemas
# -----------------------------
class TaskCreate(BaseModel):
    title: str
    due_date: Optional[datetime] = None
    notes: Optional[str] = ""
    assigned_to: Optional[str] = None

class TaskOut(TaskCreate):
    id: UUID
    tenant_id: UUID
    lead_id: UUID
    created_by: UUID
    completed: bool
    created_at: datetime
    completed_at: Optional[datetime] = None

# -----------------------------
# 📥 Create Lead
# -----------------------------
@router.post("/crm/leads", response_model=LeadOut)
async def create_lead(
    lead: LeadCreate,
    request: Request,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    lead_id = uuid4()
    created_at = datetime.utcnow()

    try:
        db.execute(
            text("""
                INSERT INTO crm_leads (
                    id, tenant_id, name, email, company, phone,
                    stage, score, rep, tags, notes, created_at
                ) VALUES (
                    :id, :tenant_id, :name, :email, :company, :phone,
                    :stage, :score, :rep, :tags, :notes, :created_at
                )
            """),
            {
                "id": lead_id,
                "tenant_id": user["tenant_id"],
                **lead.dict(),
                "created_at": created_at
            }
        )
        db.commit()

        return {
            **lead.dict(),
            "id": lead_id,
            "tenant_id": user["tenant_id"],
            "created_at": created_at
        }

    except Exception as e:
        db.rollback()
        print("❌ DB Error:", str(e))
        raise HTTPException(status_code=500, detail="Failed to create lead")

# -----------------------------
# 📤 Get Leads
# -----------------------------
@router.get("/crm/leads", response_model=List[LeadOut])
def get_leads(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        rows = db.execute(
            text("SELECT * FROM crm_leads WHERE tenant_id = :tenant_id ORDER BY created_at DESC"),
            {"tenant_id": user["tenant_id"]}
        ).mappings().all()

        return rows
    except Exception as e:
        print("❌ Error in get_leads:", e)
        raise HTTPException(status_code=500, detail="Error fetching leads")

# -----------------------------
# 📥 Add Task to Lead
# -----------------------------
@router.post("/crm/leads/{lead_id}/tasks", response_model=TaskOut)
def add_task_to_lead(
    lead_id: UUID,
    task: TaskCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task_id = uuid4()
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
        print("❌ DB Error (add_task):", e)
        raise HTTPException(status_code=500, detail="Failed to save task")

# -----------------------------
# 📤 Get Tasks for Lead
# -----------------------------
@router.get("/crm/leads/{lead_id}/tasks", response_model=List[TaskOut])
def get_tasks_for_lead(
    lead_id: UUID,
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
        print("❌ DB Error (get_tasks):", e)
        raise HTTPException(status_code=500, detail="Failed to load tasks")

# -----------------------------
# ✅ Complete a Task
# -----------------------------
@router.post("/crm/tasks/{task_id}/complete")
def mark_task_complete(
    task_id: UUID,
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
        print("❌ DB Error (complete_task):", e)
        raise HTTPException(status_code=500, detail="Failed to complete task")
