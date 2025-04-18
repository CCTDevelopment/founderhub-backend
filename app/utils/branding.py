from sqlalchemy.orm import Session
from sqlalchemy import text

def get_project_logo_base64(project_id: str, db: Session) -> str:
    row = db.execute(
        text(\"\"\"
        SELECT file_base64 FROM project_assets
        WHERE project_id = :project_id AND type = 'logo'
        ORDER BY updated_at DESC
        LIMIT 1
        \"\"\"),
        {"project_id": project_id}
    ).fetchone()

    if row:
        return row.file_base64

    # Load FounderHub fallback
    with open("app/static/logo.png", "rb") as f:
        import base64
        return base64.b64encode(f.read()).decode("utf-8")
