import os
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# === Load ENV ===
load_dotenv()

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Validate required ENV ===
required_env = ["JWT_SECRET", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "MS_TENANT_ID", "MS_SENDER_EMAIL", "DATABASE_URL"]
missing = [var for var in required_env if not os.getenv(var)]
if missing:
    logger.warning(f"⚠️ Missing required .env variables: {', '.join(missing)}")
else:
    logger.info("✅ All critical environment variables loaded.")

# === Config ===
from app.core.config import load_config

# === Routers ===
from app.api.v1 import auth, ideas, idea_chat
from app.routes import (
    waitlist,
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
    cmo_design,
    scheduler,
    contacts,
    projects,
)
from app.routes.crm import crm_leads, crm_tasks, crm_notes

# === App lifecycle ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await load_config()
        logger.info("✅ Startup complete: config loaded.")
        yield
    except Exception as e:
        logger.exception("❌ Startup failed.")
        raise e
    finally:
        logger.info("🛑 Shutdown complete.")

# === Initialize App ===
app = FastAPI(
    title="FounderHub API",
    version="1.0.0",
    lifespan=lifespan
)

# === Global Exception Handler ===
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print("⚠️ Validation Error:", exc.errors())
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# === CORS ===
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

# === Health Check ===
@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "FounderHub API is live"}

# === Mount API Routes ===
# Core
app.include_router(auth.router, prefix="/api")
app.include_router(ideas.router, prefix="/api")
app.include_router(idea_chat.router, prefix="/api")

# CRM
app.include_router(crm_leads.router, prefix="/api")
app.include_router(crm_tasks.router, prefix="/api")
app.include_router(crm_notes.router, prefix="/api")

# Modules
app.include_router(waitlist.router, prefix="/api")
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
app.include_router(cmo_design.router, prefix="/api/cmo/design")
app.include_router(scheduler.router, prefix="/api/scheduler")
app.include_router(projects.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")

# === Dev Hot Reload ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=os.getenv("ENV") == "dev")
