from uuid import uuid4
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.prompt_engine import analyze_with_ai, summarize_with_ai
from app.utils.pdf_email import render_pdf, render_docx, send_email_with_attachment
from app.schemas.idea import IdeaCreate


def get_idea(id, user, db):
    result = db.execute(
        text("SELECT * FROM ideas WHERE id = :id AND user_id = :user_id"),
        {"id": str(id), "user_id": user["id"]}
    ).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Idea not found")
    return result


def get_user_plan(user, db):
    plan = db.execute(
        text("SELECT p.max_tokens FROM user_plans p JOIN users u ON u.plan_id = p.id WHERE u.id = :user_id"),
        {"user_id": user["id"]}
    ).fetchone()
    if not plan:
        raise HTTPException(status_code=400, detail="User has no assigned plan")
    return plan


def get_monthly_usage(user, db):
    start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return db.execute(
        text("SELECT COALESCE(SUM(tokens_used), 0) FROM token_usage WHERE user_id = :user_id AND created_at >= :start"),
        {"user_id": user["id"], "start": start}
    ).scalar()


async def analyze_idea_logic(id, user, db):
    idea = get_idea(id, user, db)
    plan = get_user_plan(user, db)
    used = get_monthly_usage(user, db)

    result, tokens_used = await analyze_with_ai(idea, plan.max_tokens, used, user, db)

    if used + tokens_used > plan.max_tokens:
        raise HTTPException(status_code=403, detail="Token quota exceeded")

    db.execute(
        text("UPDATE ideas SET vetting_response = :result, vetting_status = 'analyzed', tokens_used = :tokens, updated_at = NOW() WHERE id = :id AND user_id = :user_id"),
        {"result": result, "tokens": tokens_used, "id": str(id), "user_id": user["id"]}
    )

    db.execute(
        text("INSERT INTO token_usage (id, user_id, idea_id, tokens_used, created_at) VALUES (:id, :user_id, :idea_id, :tokens_used, NOW())"),
        {"id": str(uuid4()), "user_id": user["id"], "idea_id": str(id), "tokens_used": tokens_used}
    )

    # ✅ Insert the analysis into chat log
    db.execute(text("""
        INSERT INTO idea_chat_log (id, idea_id, user_id, role, message)
        VALUES (:id, :idea_id, :user_id, 'assistant', :message)
    """), {
        "id": str(uuid4()),
        "idea_id": str(id),
        "user_id": user["id"],
        "message": result
    })

    # ✅ Trigger summary generation (which will now also log to chat)
    await summarize_idea(id, user, db)

    db.commit()

    return {
        "vetting_response": result,
        "vetting_status": "analyzed",
        "tokens_used": tokens_used,
        "tokens_remaining": plan.max_tokens - used - tokens_used
    }


def create_idea(payload: IdeaCreate, user, db):
    idea_id = str(uuid4())
    now = datetime.utcnow()
    db.execute(
        text("""INSERT INTO ideas (id, tenant_id, user_id, title, problem, audience, solution, notes, vetting_status, created_at, updated_at)
        VALUES (:id, :tenant_id, :user_id, :title, :problem, :audience, :solution, :notes, 'pending', :created_at, :updated_at)"""),
        {
            "id": idea_id,
            "tenant_id": user["tenant_id"],
            "user_id": user["id"],
            "title": payload.title,
            "problem": payload.problem,
            "audience": payload.audience,
            "solution": payload.solution,
            "notes": payload.notes,
            "created_at": now,
            "updated_at": now
        }
    )
    db.commit()
    return {
        "id": idea_id,
        "title": payload.title,
        "problem": payload.problem,
        "audience": payload.audience,
        "solution": payload.solution,
        "notes": payload.notes,
        "vetting_status": "pending",
        "vetting_response": None
    }


def get_all_ideas(user, db):
    result = db.execute(
        text("""
        SELECT i.id, i.title, i.problem, i.audience, i.solution, i.notes, i.vetting_status, i.vetting_response, s.summary
        FROM ideas i
        LEFT JOIN idea_summary s ON s.idea_id = i.id
        WHERE i.user_id = :user_id
        ORDER BY i.created_at DESC
        """),
        {"user_id": user["id"]}
    )
    return [dict(row._mapping) for row in result.fetchall()]


def get_idea_detail(id, user, db):
    result = get_idea(id, user, db)
    return dict(result._mapping)


def export_idea_email(id, format_type, user, db):
    idea = get_idea(id, user, db)
    messages = db.execute(
        text("SELECT role, message FROM idea_chat_log WHERE idea_id = :id AND user_id = :user_id ORDER BY created_at"),
        {"id": str(id), "user_id": user["id"]}
    ).fetchall()
    token_used = get_monthly_usage(user, db)
    plan = get_user_plan(user, db)
    score = db.execute(text("SELECT viability_score FROM ideas WHERE id = :id AND user_id = :user_id"),
        {"id": str(id), "user_id": user["id"]}).scalar()
    data = {
        "idea": idea,
        "messages": [{"role": m.role, "message": m.message} for m in messages],
        "tokens_used": token_used,
        "token_limit": plan.max_tokens,
        "score": score or "N/A",
        "date": datetime.utcnow().strftime("%B %d, %Y")
    }

    formats = []
    if format_type in ["pdf", "both"]:
        formats.append(("PDF", render_pdf(data)))
    if format_type in ["docx", "both"]:
        formats.append(("DOCX", render_docx(data)))

    for label, path in formats:
        send_email_with_attachment(user["email"], f"📎 Your FounderHub Deep Dive Report ({label})", f"<p>Here’s your Deep Dive summary as a {label}.</p>", path)

    return {"detail": f"Deep Dive {format_type.upper()} sent to {user['email']}"}


async def summarize_idea(id, user, db):
    idea = get_idea(id, user, db)
    chat = db.execute(
        text("SELECT role, message FROM idea_chat_log WHERE idea_id = :id AND user_id = :user_id ORDER BY created_at"),
        {"id": str(id), "user_id": user["id"]}
    ).fetchall()
    score = db.execute(text("SELECT viability_score FROM ideas WHERE id = :id AND user_id = :user_id"),
        {"id": str(id), "user_id": user["id"]}).scalar()
    
    summary, team = await summarize_with_ai(idea, chat, score, user, db)

    # ✅ Insert the summary into the chat log
    db.execute(text("""
        INSERT INTO idea_chat_log (id, idea_id, user_id, role, message)
        VALUES (:id, :idea_id, :user_id, 'assistant', :message)
    """), {
        "id": str(uuid4()),
        "idea_id": str(id),
        "user_id": user["id"],
        "message": summary
    })

    db.execute(text("""
        INSERT INTO idea_summary (id, idea_id, user_id, summary, recommended_team)
        VALUES (:id, :idea_id, :user_id, :summary, :team)
        ON CONFLICT (idea_id) DO UPDATE SET
        summary = EXCLUDED.summary,
        recommended_team = EXCLUDED.recommended_team
    """),
        {"id": str(uuid4()), "idea_id": str(id), "user_id": user["id"], "summary": summary, "team": team})

    db.execute(text("""
        INSERT INTO project_plan (project_id, content_html, created_at, updated_at)
        VALUES (:project_id, :content_html, NOW(), NOW())
        ON CONFLICT (project_id) DO UPDATE SET
        content_html = EXCLUDED.content_html,
        updated_at = NOW()
    """),
        {"project_id": str(id), "content_html": summary})

    db.commit()
    return {"summary": summary, "recommended_team": team}
