# ✅ app/utils/document_template.py

from sqlalchemy import text
from app.documents.template import ProjectDocumentTemplate
import base64
import os


def get_project_logo_base64(project_id: str, db):
    row = db.execute(
        text("""
        SELECT file_base64 FROM project_assets
        WHERE project_id = :project_id AND type = 'logo'
        ORDER BY updated_at DESC LIMIT 1
        """),
        {"project_id": project_id}
    ).fetchone()

    if row:
        return row.file_base64

    # Fallback to default FounderHub logo
    fallback_path = "app/static/logo.png"
    if os.path.exists(fallback_path):
        with open(fallback_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return None


def build_project_document(project, user, db, sections: dict, output_path: str):
    logo_base64 = get_project_logo_base64(str(project.id), db)
    template = ProjectDocumentTemplate(project, user, db)
    template.add_cover_page(logo_base64)
    template.add_table_of_contents()

    for heading, content in sections.items():
        template.add_section(heading, content)

    template.save(output_path)
    return output_path
