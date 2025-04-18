from app.models.idea import Idea
from app.models.sparring_template import SparringTemplate
from sqlalchemy.orm import Session
from jinja2 import Template

def get_rendered_prompt(project_id, role, db: Session) -> str:
    idea = db.query(Idea).filter_by(id=project_id).first()
    if not idea:
        raise Exception("Idea not found.")

    template = db.query(SparringTemplate).filter_by(role=role.lower()).first()
    if not template:
        raise Exception(f"Sparring prompt for role '{role}' not found.")

    try:
        tpl = Template(template.template_text)
        return tpl.render(
            idea_name=idea.title,  # ✅ Fixed: use `title`
            idea_summary=idea.solution or "No summary provided yet."  # ✅ Use actual field
        )
    except Exception:
        return f"You are the {role.upper()} of a startup. Help the founder make high-quality decisions."
