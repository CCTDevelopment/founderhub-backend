from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from sqlalchemy import text
from fastapi.responses import FileResponse
from app.core.db import get_db
from app.dependencies.auth import get_current_user
from app.documents.document_template import build_project_document
from app.utils.llm_client import run_gpt_task
import os

router = APIRouter()

# -----------------------------
# 📥 Create Project
# -----------------------------
@router.post("/projects")
def create_project(payload: dict, user=Depends(get_current_user), db: Session = Depends(get_db)):
    project_id = str(uuid4())

    db.execute(
        text("""
            INSERT INTO projects (id, tenant_id, title, description, type, status, created_at)
            VALUES (:id, :tenant_id, :title, :description, :type, 'idea', NOW())
        """),
        {
            "id": project_id,
            "tenant_id": user["tenant_id"],
            "title": payload.get("title"),
            "description": payload.get("description"),
            "type": payload.get("type") or "general"
        }
    )
    db.commit()

    return {"id": project_id, "title": payload["title"]}

# -----------------------------
# 📤 List Projects
# -----------------------------
@router.get("/projects")
def list_projects(user=Depends(get_current_user), db: Session = Depends(get_db)):
    result = db.execute(
        text("""
            SELECT id, title, description, type, status
            FROM projects
            WHERE tenant_id = :tenant_id
            ORDER BY created_at DESC
        """),
        {"tenant_id": user["tenant_id"]}
    ).fetchall()

    return [dict(row._mapping) for row in result]

# -----------------------------
# 📥 Generate Business Plan (POST)
# -----------------------------
@router.post("/projects/{project_id}/generate-business-plan")
def generate_business_plan(
    project_id: UUID,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.execute(
        text("SELECT * FROM projects WHERE id = :id AND tenant_id = :tenant_id"),
        {"id": str(project_id), "tenant_id": user["tenant_id"]}
    ).fetchone()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    summary_row = db.execute(
        text("SELECT content_html FROM project_plan WHERE project_id = :id"),
        {"id": str(project_id)}
    ).fetchone()
    summary = summary_row.content_html if summary_row else ""

    chat_rows = db.execute(
        text("""
            SELECT role, message
            FROM idea_chat_log
            WHERE idea_id = :id
            ORDER BY created_at
        """),
        {"id": str(project_id)}
    ).fetchall()
    chat_log = "\n".join([f"{r.role.capitalize()}: {r.message}" for r in chat_rows])

    prompt = f"""
You are the CEO of a startup. Based on the summary and chat, write a business plan:

- Executive Summary
- Business Model
- Product Vision
- Monetization Strategy
- Market & Opportunity
- Go-To-Market Strategy
- Hiring Plan
- Financials
- Key Milestones
- Risk & Mitigation

---

Summary:
{summary}

---

Chat Transcript:
{chat_log}
"""

    business_plan = run_gpt_task(prompt, system="You are a startup CEO generating a business plan.")

    db.execute(
        text("""
            INSERT INTO assistant_outputs (id, project_id, role, content, created_at)
            VALUES (:id, :project_id, 'ceo', :content, NOW())
        """),
        {
            "id": str(uuid4()),
            "project_id": str(project_id),
            "content": business_plan
        }
    )
    db.commit()

    return {"content": business_plan}

# -----------------------------
# 📤 Get Existing Business Plan (GET)
# -----------------------------
@router.get("/projects/{project_id}/business-plan")
def get_business_plan(
    project_id: UUID,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    row = db.execute(
        text("""
            SELECT content
            FROM assistant_outputs
            WHERE project_id = :project_id AND role = 'ceo'
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"project_id": str(project_id)}
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No business plan found")

    return {"content": row.content}

# -----------------------------
# 📁 Generate Project Document (Download .docx)
# -----------------------------
@router.get("/projects/{project_id}/generate-doc")
def generate_project_document(
    project_id: UUID,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.execute(
        text("SELECT * FROM projects WHERE id = :id AND tenant_id = :tenant_id"),
        {"id": str(project_id), "tenant_id": user["tenant_id"]}
    ).fetchone()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sections = {
        "Executive Summary": "This is a generated executive summary for your project.",
        "Problem & Solution": "Describe the problem and how you're solving it.",
        "Market & Opportunity": "Market analysis goes here.",
        "Product Vision": "The big idea behind your product.",
        "Team & Advisors": "Your AI board or human team.",
        "Go-to-Market Strategy": "Channels, budget, and strategy.",
        "Financial Overview": "Estimates, burn rate, runway.",
        "Risks & Mitigations": "What could go wrong and how you'll fix it.",
        "Board Decision": "AI board's verdict or user-generated consensus.",
        "Appendices": "Optional reference material or attachments."
    }

    file_path = f"/tmp/founderhub_{project_id}.docx"
    build_project_document(project, user, db, sections, file_path)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=500, detail="Document generation failed.")

    return FileResponse(
        file_path,
        filename=os.path.basename(file_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

# -----------------------------
# 📤 Get Doc Content for Display
# -----------------------------
@router.get("/projects/{project_id}/generate-doc-content")
def get_project_doc_content(
    project_id: UUID,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.execute(
        text("SELECT * FROM projects WHERE id = :id AND tenant_id = :tenant_id"),
        {"id": str(project_id), "tenant_id": user["tenant_id"]}
    ).fetchone()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sections = {
        "Executive Summary": "This is an executive summary about your project...",
        "Problem & Solution": "Here's the problem you're solving...",
        "Market & Opportunity": "Market insights go here...",
        "Product Vision": "What the product aims to be...",
        "Team & Advisors": "Your AI board or human team here...",
        "Go-to-Market Strategy": "Initial launch, growth, and scale plan...",
        "Financial Overview": "Startup costs, burn rate, and revenue model...",
        "Risks & Mitigations": "Known risks and how you’ll handle them...",
        "Board Decision": "What your AI board said...",
        "Appendices": "Additional data and attachments..."
    }

    return {
        "project_title": project.title,
        "sections": sections
    }

# -----------------------------
# 📊 Summary Page for Project
# -----------------------------
@router.get("/projects/{project_id}/summary")
def get_project_summary(
    project_id: UUID,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.execute(
        text("SELECT * FROM projects WHERE id = :id AND tenant_id = :tenant_id"),
        {"id": str(project_id), "tenant_id": user["tenant_id"]}
    ).fetchone()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    summary_row = db.execute(
        text("""
            SELECT content_html
            FROM project_plan
            WHERE project_id = :id
            LIMIT 1
        """),
        {"id": str(project_id)}
    ).fetchone()

    team_row = db.execute(
        text("""
            SELECT recommended_team
            FROM idea_summary
            WHERE idea_id = :id
            LIMIT 1
        """),
        {"id": str(project_id)}
    ).fetchone()

    return {
        "summary": summary_row.content_html if summary_row else "",
        "recommended_team": team_row.recommended_team if team_row else ""
    }
