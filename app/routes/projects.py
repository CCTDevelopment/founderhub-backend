from fastapi import APIRouter, HTTPException
from app.models import ProjectCreate
from app.db import get_db_connection

router = APIRouter()

@router.post("/api/projects")
async def create_project(project: ProjectCreate):
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO projects (name, description, email)
            VALUES ($1, $2, $3)
            """,
            project.name, project.description, project.email
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not create project.")
    finally:
        await conn.close()
    
    return {"message": "Project created"}

@router.get("/api/projects")
async def list_projects():
    conn = await get_db_connection()
    rows = await conn.fetch("SELECT id, name, description, email, created_at FROM projects")
    await conn.close()
    return [dict(row) for row in rows]
