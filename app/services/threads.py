from app.models.project_threads import ProjectThread
from sqlalchemy.orm import Session
from uuid import uuid4

def save_thread(project_id, role, assistant_id, thread_id, tenant_id, user_id, db: Session):
    existing = db.query(ProjectThread).filter_by(project_id=project_id, role=role).first()
    if existing:
        existing.thread_id = thread_id
        existing.assistant_id = assistant_id
        existing.updated_at = func.now()
    else:
        db.add(ProjectThread(
            id=uuid4(),
            project_id=project_id,
            role=role,
            assistant_id=assistant_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id
        ))
    db.commit()

def get_thread(project_id, role, db: Session):
    return db.query(ProjectThread).filter_by(project_id=project_id, role=role).first()
