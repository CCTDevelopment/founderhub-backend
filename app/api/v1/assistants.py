from sqlalchemy.orm import Session
from uuid import uuid4
from openai import AsyncOpenAI
from jinja2 import Template

from app.models.idea import Idea
from app.models.project_threads import ProjectThread
from app.models.sparring_template import SparringTemplate

client = AsyncOpenAI()


async def ensure_assistant_for_role(
    project_id: str,
    role: str,
    user: dict,
    db: Session
) -> str:
    role = role.lower()

    # Check if assistant + thread already exist for this role/project/user
    existing = db.query(ProjectThread).filter_by(
        project_id=project_id,
        role=role,
        tenant_id=user["tenant_id"],
        user_id=user["id"]
    ).first()

    if existing:
        return existing.assistant_id

    # Load the project/idea for context
    idea = db.query(Idea).filter_by(id=project_id).first()
    if not idea:
        raise Exception("Project idea not found.")

    # Fetch dynamic system prompt using the project's name/summary
    prompt = get_dynamic_prompt(
        role=role,
        idea_name=idea.name,
        idea_summary=idea.summary or "No summary provided yet.",
        db=db
    )

    # Create the new OpenAI assistant
    assistant = await client.beta.assistants.create(
        name=f"{idea.name} {role.upper()}",
        instructions=prompt,
        model="gpt-4o"
    )

    # Create a new memory thread for the assistant
    thread = await client.beta.threads.create()

    # Save assistant/thread details to project_threads table
    db.add(ProjectThread(
        id=uuid4(),
        project_id=project_id,
        role=role,
        assistant_id=assistant.id,
        thread_id=thread.id,
        tenant_id=user["tenant_id"],
        user_id=user["id"]
    ))

    db.commit()
    return assistant.id


def get_dynamic_prompt(role: str, idea_name: str, idea_summary: str, db: Session) -> str:
    role = role.lower()

    template_obj = db.query(SparringTemplate).filter_by(role=role).first()
    if not template_obj:
        return f"You are the {role.upper()} of a startup. Help the founder make high-quality decisions."

    try:
        tpl = Template(template_obj.template_text)
        return tpl.render(
            idea_name=idea_name,
            idea_summary=idea_summary
        )
    except Exception:
        return f"You are the {role.upper()} of a startup. Help the founder make high-quality decisions."
