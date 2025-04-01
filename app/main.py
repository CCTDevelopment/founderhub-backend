from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.services.analytics.kb_collector import collect_kpi_snapshots

from app.routes import ga
# 🔌 Import all route modules
from app.routes import (
    waitlist,
    projects,
    ai_agents,
    ai_chats,
    personality,
    board,
    documents
)

from app.api.v1 import (
    auth,
    ideas,
    idea_chat  # 👈 your new deep-dive GPT endpoint
)

app = FastAPI(title="FounderHub API", version="1.0.0")

# 🔥 CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://portal.founderhub.ai",
        "https://founderhub.ai",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Healthcheck route
@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "FounderHub API is live"}

# ✅ API Routers
app.include_router(auth.router, prefix="/api")
app.include_router(ideas.router, prefix="/api")
app.include_router(idea_chat.router, prefix="/api")  # 💬 GPT deep dive chat

app.include_router(waitlist.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(ai_agents.router, prefix="/api")
app.include_router(ai_chats.router, prefix="/api")
app.include_router(personality.router, prefix="/api")
app.include_router(board.router, prefix="/api")
app.include_router(documents.router, prefix="/api")

app.include_router(ga.router)
collect_kpi_snapshots(db, site_id=site_id)
