from uuid import uuid4
from sqlalchemy.orm import Session
from openai import AsyncOpenAI
from jinja2 import Template, TemplateError

from app.models.idea import Idea
from app.models.sparring_template import SparringTemplate
from app.models.project_threads import ProjectThread

client = AsyncOpenAI()

# ✅ Main entry point
async def ensure_assistant_for_role(
    project_id: str,
    role: str,
    user: dict,
    db: Session
) -> str:
    role = role.lower()

    # 🧠 Check if assistant + thread already exist
    existing = db.query(ProjectThread).filter_by(
        project_id=project_id,
        role=role,
        tenant_id=user["tenant_id"],
        user_id=user["id"]
    ).first()

    if existing:
        return existing.assistant_id

    # 🚀 Create new assistant and thread
    assistant_id, _ = await get_or_create_assistant_and_thread(
        db=db,
        user_id=user["id"],
        tenant_id=user["tenant_id"],
        project_id=project_id,
        role=role
    )

    return assistant_id

# 🔧 Builds assistant + thread from scratch
async def get_or_create_assistant_and_thread(
    db: Session,
    user_id: str,
    tenant_id: str,
    project_id: str,
    role: str
) -> tuple[str, str]:
    role = role.lower()

    idea = db.query(Idea).filter_by(id=project_id).first()
    if not idea:
        raise ValueError("⚠️ Project idea not found.")

    instructions = generate_instructions_by_role(role=role, db=db, project_id=project_id)

    # 🧠 Create assistant using OpenAI
    try:
        assistant = await client.beta.assistants.create(
            name=f"{idea.title} — {role.upper()}",
            instructions=instructions,
            model="gpt-4o"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to create assistant: {e}")

    # 🔗 Create thread
    try:
        thread = await client.beta.threads.create()
    except Exception as e:
        raise RuntimeError(f"Failed to create thread: {e}")

    # 💾 Save to DB
    db.add(ProjectThread(
        id=str(uuid4()),
        project_id=project_id,
        role=role,
        assistant_id=assistant.id,
        thread_id=thread.id,
        tenant_id=tenant_id,
        user_id=user_id
    ))
    db.commit()

    return assistant.id, thread.id

# 🧠 Loads + renders the correct prompt template
def generate_instructions_by_role(
    role: str,
    db: Session,
    project_id: str
) -> str:
    role = role.lower()

    idea = db.query(Idea).filter_by(id=project_id).first()
    if not idea:
        raise ValueError("Idea not found.")

    template = db.query(SparringTemplate).filter_by(role=role).first()
    if not template:
        return f"You are the {role.upper()} of a startup. Help the founder make high-quality decisions."

    try:
        tpl = Template(template.template_text)
        return tpl.render(
            idea_name=idea.title,
            idea_summary=idea.solution or "No summary provided yet."
        )
    except TemplateError as e:
        return f"You are the assistant for {role.upper()}, but the prompt failed to render. Error: {e}"
