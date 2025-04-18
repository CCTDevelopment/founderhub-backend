from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from sqlalchemy.orm import Session
from app.dependencies.auth import get_current_user
from app.core.db import get_db
from app.models.project_threads import ProjectThread

router = APIRouter()

@router.get("/ideas/{project_id}/team")
def get_project_team(
    project_id: UUID,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    threads = db.query(ProjectThread).filter_by(
        project_id=project_id,
        tenant_id=user["tenant_id"],
        user_id=user["id"]
    ).all()

    if not threads:
        raise HTTPException(status_code=404, detail="No assistants found for this project.")

    roles = [t.role for t in threads]
    assistant_map = {t.role: t.assistant_id for t in threads}

    return {
        "roles": roles,
        "assistants": assistant_map
    }
