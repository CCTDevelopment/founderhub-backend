from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging

# Import routers from various modules
from app.api.v1 import auth, ideas, idea_chat
from app.routes import (
    waitlist,
    projects,
    ai_agents,
    ai_chats,
    personality,
    board,
    documents,
    ga,
    facebook_posts,
    linkedin_posts,
    free_advertising,
    growth_hacker,
    cmo_design_full,
    scheduler
)

# Import our configuration loader and database instance from a central module (e.g., from cmo_design_full)
from app.routes.cmo_design_full import load_config, database

# Optionally, import KPI snapshot collector if needed
from app.services.analytics.kb_collector import collect_kpi_snapshots

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FounderHub API", version="1.0.0")

# CORS configuration (update these origins as needed)
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

# Health check endpoint
@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "FounderHub API is live"}

# Include API routers with appropriate prefixes
app.include_router(auth.router, prefix="/api")
app.include_router(ideas.router, prefix="/api")
app.include_router(idea_chat.router, prefix="/api")  # Deep-dive GPT chat

app.include_router(waitlist.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(ai_agents.router, prefix="/api")
app.include_router(ai_chats.router, prefix="/api")
app.include_router(personality.router, prefix="/api")
app.include_router(board.router, prefix="/api")
app.include_router(documents.router, prefix="/api")

app.include_router(ga.router, prefix="/api/ga")
app.include_router(facebook_posts.router, prefix="/api/facebook/posts")
app.include_router(linkedin_posts.router, prefix="/api/linkedin/posts")
app.include_router(free_advertising.router, prefix="/api/free-advertising")
app.include_router(growth_hacker.router, prefix="/api/growth-hacker")
app.include_router(cmo_design_full.router, prefix="/api/cmo/design")
app.include_router(scheduler.router, prefix="/api/scheduler")

# Startup event: Connect to the database and load configuration from the system_config table.
@app.on_event("startup")
async def startup_event():
    await database.connect()
    await load_config()  # This loads API keys (OPENAI_API_KEY, FB_PAGE_TOKEN, etc.) from the database.
    logger.info("Startup complete: Database connected and configuration loaded.")
    
    # Optionally, schedule periodic tasks (e.g., KPI snapshot collection)
    # Example: await collect_kpi_snapshots(database, site_id="your_site_id")

# Shutdown event: Disconnect from the database.
@app.on_event("shutdown")
async def shutdown_event():
    await database.disconnect()
    logger.info("Shutdown complete: Database disconnected.")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
