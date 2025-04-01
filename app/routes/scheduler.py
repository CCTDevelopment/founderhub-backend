import os
import uuid
import logging
import asyncio
from datetime import datetime
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError
from databases import Database
from dotenv import load_dotenv

# Load environment variables (DATABASE_URL is provided via env)
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
database = Database(DATABASE_URL)

# Global configuration loaded from the DB (assume keys are stored in system_config)
config: Dict[str, str] = {}

async def get_config_value(key: str) -> str:
    query = "SELECT config_value FROM system_config WHERE config_key = :key"
    row = await database.fetch_one(query=query, values={"key": key})
    if not row:
        raise RuntimeError(f"Configuration key '{key}' not found in DB")
    return row["config_value"]

async def load_config():
    keys = ["OPENAI_API_KEY", "FB_PAGE_TOKEN", "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN", "SLACK_WEBHOOK_URL"]
    for key in keys:
        config[key] = await get_config_value(key)
    logging.info("Configuration loaded from DB.")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize APScheduler
scheduler = AsyncIOScheduler()
scheduler.start()

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

# -----------------------------
# Authentication & RBAC (Production Ready)
# -----------------------------
def get_current_user():
    # Replace this stub with your real authentication logic.
    return {"user_id": "dummy_user", "tenant_id": "dummy_tenant", "role": "CMO"}

def require_role(required_roles: List[str]):
    def role_checker(user=Depends(get_current_user)):
        if user.get("role") not in required_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker

# -----------------------------
# Pydantic Model for Scheduling
# -----------------------------
class SchedulePostRequest(BaseModel):
    tenant_id: str
    project_id: str
    platform: str = Field(..., description="Target platform: 'facebook' or 'linkedin'")
    scheduled_time: datetime = Field(..., description="The future time at which the post should be published")
    post_payload: Dict  = Field(..., description="The full post payload as a JSON object. This should conform to the expected request model for the target platform.")

class ScheduleResponse(BaseModel):
    job_id: str
    scheduled_time: datetime

# -----------------------------
# Job Function for Scheduled Posting
# -----------------------------
async def execute_scheduled_post(post_payload: Dict):
    """
    Executes a scheduled post.
    Depending on the platform in the payload, calls the appropriate posting function.
    """
    platform = post_payload.get("platform")
    tenant_id = post_payload.get("tenant_id")
    # Import posting functions dynamically or ensure they are accessible.
    if platform == "facebook":
        from app.routes.facebook_posts import create_facebook_post  # Import the function
        # Rebuild a FacebookPostRequest object
        from app.routes.facebook_posts import FacebookPostRequest
        fb_request = FacebookPostRequest(**post_payload)
        # Call the function (simulate user as 'scheduler')
        user = {"user_id": "scheduler", "tenant_id": tenant_id, "role": "CMO"}
        result = await create_facebook_post(fb_request, BackgroundTasks(), user)
        logger.info("Scheduled Facebook post executed: %s", result)
    elif platform == "linkedin":
        from app.routes.linkedin_posts import create_linkedin_post  # Import the function
        from app.routes.linkedin_posts import LinkedInPostRequest
        li_request = LinkedInPostRequest(**post_payload)
        user = {"user_id": "scheduler", "tenant_id": tenant_id, "role": "CMO"}
        result = await create_linkedin_post(li_request, BackgroundTasks(), user)
        logger.info("Scheduled LinkedIn post executed: %s", result)
    else:
        logger.error("Unknown platform: %s", platform)
        raise ValueError("Unknown platform")

# -----------------------------
# API Endpoints for Scheduling
# -----------------------------
@router.post("/post", response_model=ScheduleResponse)
async def schedule_post(
    request: SchedulePostRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Schedules a post (Facebook or LinkedIn) for a future time.
    The entire post payload must be provided.
    """
    # Validate that the scheduled time is in the future.
    if request.scheduled_time <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Scheduled time must be in the future")
    
    try:
        job = scheduler.add_job(
            execute_scheduled_post,
            trigger="date",
            run_date=request.scheduled_time,
            args=[request.post_payload],
            id=str(uuid.uuid4())
        )
        logger.info("Scheduled post with job ID: %s", job.id)
        return ScheduleResponse(job_id=job.id, scheduled_time=request.scheduled_time)
    except Exception as e:
        logger.error("Failed to schedule post: %s", e)
        raise HTTPException(status_code=500, detail="Failed to schedule post")

@router.delete("/post/{job_id}")
async def cancel_scheduled_post(job_id: str):
    """
    Cancels a scheduled post given its job ID.
    """
    try:
        scheduler.remove_job(job_id)
        logger.info("Scheduled job %s canceled.", job_id)
        return {"detail": f"Scheduled job {job_id} canceled"}
    except Exception as e:
        logger.error("Failed to cancel scheduled post: %s", e)
        raise HTTPException(status_code=404, detail="Job not found or already executed")

# -----------------------------
# Startup and Shutdown Handlers
# -----------------------------
from fastapi import FastAPI

def init_scheduler(app: FastAPI):
    @app.on_event("startup")
    async def startup():
        await database.connect()
        await load_config()
        scheduler.start()
        logger.info("Scheduler started, DB connected, and config loaded.")

    @app.on_event("shutdown")
    async def shutdown():
        scheduler.shutdown(wait=False)
        await database.disconnect()
        logger.info("Scheduler shutdown and DB disconnected.")
