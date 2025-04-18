from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.core.db import get_db
from app.services.idea_service import (
    analyze_idea_logic,
    create_idea,
    get_all_ideas,
    get_idea_detail,
    export_idea_email,
    summarize_idea,
)
from app.schemas.idea import IdeaCreate
from app.services.assistant_service import ensure_assistant_for_role

router = APIRouter()

@router.post("/ideas/{id}/analyze")
async def analyze_idea(id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return await analyze_idea_logic(id, user, db)

@router.post("/ideas")
def create_idea_route(payload: IdeaCreate, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return create_idea(payload, user, db)

@router.get("/ideas")
def list_ideas(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return get_all_ideas(user, db)

@router.get("/ideas/{id}")
def get_idea(id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return get_idea_detail(id, user, db)

@router.post("/ideas/{id}/export-email")
def export_email(id: UUID, format_type: str = "pdf", user=Depends(get_current_user), db: Session = Depends(get_db)):
    return export_idea_email(id, format_type, user, db)

@router.post("/ideas/{id}/summarize")
async def summarize(id: UUID, user=Depends(get_current_user), db: Session = Depends(get_db)):
    result = await summarize_idea(id, user, db)
    
    # 🔁 Create CEO assistant after idea summary
    await ensure_assistant_for_role(id, role="ceo", user=user, db=db)
    
    return result
