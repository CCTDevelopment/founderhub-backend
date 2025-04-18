from sqlalchemy.orm import Session
from app.services.assistant_service import ensure_assistant_for_role
from app.stella_sdk.runner import run_assistant
from app.models.idea import Idea


# 🔍 Analyze an idea from the AI’s point of view (CEO or critic role)
async def analyze_with_ai(idea: Idea, token_limit: int, used: int, user: dict, db: Session):
    base_text = f"""
Title: {idea.title}
Problem: {idea.problem}
Audience: {idea.audience}
Solution: {idea.solution}
Notes: {idea.notes or "N/A"}
"""

    role = "startup_critic"
    assistant_id = await ensure_assistant_for_role(str(idea.id), role, user, db)

    # ✅ Await assistant execution
    gpt_reply, thread_id = await run_assistant(
        project_id=str(idea.id),
        role=role,
        message=base_text,
        assistant_id=assistant_id,
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        db=db
    )

    tokens = 800  # This is your estimated usage
    return gpt_reply, tokens


# 🧠 Summarize a transcript of chat messages about the startup
async def summarize_with_ai(
    idea: Idea,
    chat_messages: list[dict],  # Must be a list of dicts: [{ role, message }]
    score: int | None,
    user: dict,
    db: Session
):
    role = "summarizer"
    project_id = str(idea.id)

    # ✅ Build conversation transcript cleanly
    transcript = "\n".join([
        f"{m['role'].title()}: {m['message']}"
        for m in chat_messages if isinstance(m, dict) and 'role' in m and 'message' in m
    ])

    prompt = f"""You are a strategic product consultant AI.
Your job is to analyze the conversation below and return a clear, structured startup summary.

Startup Info:
Title: {idea.title}
Problem: {idea.problem}
Audience: {idea.audience}
Solution: {idea.solution}
Viability Score: {score or 'N/A'}

Transcript:
{transcript}
"""

    assistant_id = await ensure_assistant_for_role(project_id, role, user, db)

    # ✅ Await assistant execution
    response, _ = await run_assistant(
        project_id=project_id,
        role=role,
        message=prompt,
        assistant_id=assistant_id,
        tenant_id=user["tenant_id"],
        user_id=user["id"],
        db=db
    )

    # ✅ Split structured summary + team section (if exists)
    if "**👥 Recommended Team:**" in response:
        summary, team = response.split("**👥 Recommended Team:**", 1)
    else:
        summary, team = response, ""

    return summary.strip(), team.strip()
