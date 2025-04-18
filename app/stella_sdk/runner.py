from app.models.project_threads import ProjectThread
from sqlalchemy.orm import Session
from openai import AsyncOpenAI
import asyncio

client = AsyncOpenAI()

async def run_assistant(
    project_id: str,
    role: str,
    message: str,
    assistant_id: str,
    tenant_id: str,
    user_id: str,
    db: Session,
    system_message: str = None,  # KEEP THIS PARAM but don't use it here
    stream: bool = False
) -> tuple[str, str]:
    # Fetch thread_id from DB
    thread = db.query(ProjectThread).filter_by(
        project_id=project_id,
        role=role,
        tenant_id=tenant_id,
        user_id=user_id
    ).first()

    if not thread:
        raise Exception("No thread found for this assistant")

    thread_id = thread.thread_id

    # Add the message to the thread
    await client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )

    run = await client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # Poll until complete
    for _ in range(30):
        run_status = await client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == "completed":
            break
        elif run_status.status == "failed":
            raise Exception("Assistant run failed")
        await asyncio.sleep(1)

    messages = await client.beta.threads.messages.list(thread_id=thread_id)

    for msg in reversed(messages.data):
        if msg.role == "assistant":
            return msg.content[0].text.value.strip(), thread_id

    raise Exception("No assistant message found")
