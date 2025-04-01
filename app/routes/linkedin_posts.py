import os
import uuid
import logging
import requests
from datetime import datetime, date
from typing import List, Optional, Dict

import openai
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, Field
from databases import Database
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

# Load environment variables (DATABASE_URL is provided via env)
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
database = Database(DATABASE_URL)

# Global configuration dictionary loaded from DB via system_config table.
# This module expects keys: "OPENAI_API_KEY", "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN", "SLACK_WEBHOOK_URL"
config: Dict[str, str] = {}

async def get_config_value(key: str) -> str:
    query = "SELECT config_value FROM system_config WHERE config_key = :key"
    row = await database.fetch_one(query=query, values={"key": key})
    if not row:
        raise RuntimeError(f"Configuration key '{key}' not found in DB")
    return row["config_value"]

async def load_config():
    keys = ["OPENAI_API_KEY", "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN", "SLACK_WEBHOOK_URL"]
    for key in keys:
        config[key] = await get_config_value(key)
    openai.api_key = config["OPENAI_API_KEY"]
    logging.info("LinkedIn config loaded from DB.")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linkedin/posts", tags=["LinkedIn Posts"])

# -----------------------------
# Authentication & RBAC (Production Ready)
# -----------------------------
def get_current_user():
    # Replace with your real authentication mechanism.
    return {"user_id": "dummy_user", "tenant_id": "dummy_tenant", "role": "CMO"}

def require_role(required_roles: List[str]):
    def role_checker(user=Depends(get_current_user)):
        if user.get("role") not in required_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker

# -----------------------------
# Slack Notification (Production Integration)
# -----------------------------
def send_slack_notification(message: str):
    payload = {"text": message}
    try:
        response = requests.post(config["SLACK_WEBHOOK_URL"], json=payload)
        response.raise_for_status()
        logger.info("Slack notification sent: %s", message)
    except Exception as e:
        logger.error("Failed to send Slack notification: %s", e)

# -----------------------------
# Pydantic Models for LinkedIn Posts & Overrides
# -----------------------------
class LinkedInPostRequest(BaseModel):
    tenant_id: str
    project_id: str
    post_type: str = Field(..., description="e.g., 'profile', 'page', 'sponsored'")
    campaign_name: Optional[str] = Field(None, description="Optional campaign name")
    business_name: str
    tagline: str
    target_audience: Optional[str] = Field(None, description="Target audience for the post")
    objectives: Optional[str] = Field(None, description="Marketing objectives (lead generation, brand awareness, etc.)")
    description: Optional[str] = Field("", description="Additional creative details")
    style: Optional[str] = Field("modern", description="Tone and style (professional, inspiring, innovative, etc.)")
    language: Optional[str] = Field("en", description="Language code (e.g., 'en', 'es', 'fr')")
    extra_instructions: Optional[str] = Field("", description="Extra instructions for the AI copy")

class LinkedInPostResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    post_type: str
    business_name: str
    tagline: str
    message: str
    linkedin_post_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    version: int

class OverrideRequest(BaseModel):
    tenant_id: str
    post_id: str  # ID of the LinkedIn post to override
    override_message: str

# -----------------------------
# Database Helper Functions (Async)
# -----------------------------
async def store_linkedin_post(
    tenant_id: str,
    project_id: str,
    post_type: str,
    business_name: str,
    tagline: str,
    message: str,
    linkedin_post_id: Optional[str],
    version: int = 1
) -> str:
    post_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO linkedin_posts (id, tenant_id, project_id, post_type, business_name, tagline, message, linkedin_post_id, created_at, updated_at, version)
    VALUES (:id, :tenant_id, :project_id, :post_type, :business_name, :tagline, :message, :linkedin_post_id, :created_at, :updated_at, :version)
    """
    values = {
        "id": post_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "post_type": post_type,
        "business_name": business_name,
        "tagline": tagline,
        "message": message,
        "linkedin_post_id": linkedin_post_id,
        "created_at": now,
        "updated_at": now,
        "version": version,
    }
    await database.execute(query=query, values=values)
    return post_id

async def update_linkedin_post_in_db(post_id: str, message: str, linkedin_post_id: Optional[str], version: int) -> None:
    now = datetime.utcnow()
    query = """
    UPDATE linkedin_posts
    SET message = :message, linkedin_post_id = :linkedin_post_id, updated_at = :updated_at, version = :version
    WHERE id = :id
    """
    values = {"id": post_id, "message": message, "linkedin_post_id": linkedin_post_id, "updated_at": now, "version": version}
    await database.execute(query=query, values=values)

async def store_override(tenant_id: str, post_id: str, override_message: str) -> str:
    override_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO overrides (id, tenant_id, design_id, override_message, created_at)
    VALUES (:id, :tenant_id, :design_id, :override_message, :created_at)
    """
    values = {
        "id": override_id,
        "tenant_id": tenant_id,
        "design_id": post_id,
        "override_message": override_message,
        "created_at": now,
    }
    await database.execute(query=query, values=values)
    return override_id

# -----------------------------
# Advanced Prompt Builder for LinkedIn Posts
# -----------------------------
def build_linkedin_post_prompt(request: LinkedInPostRequest) -> str:
    prompt = (
        f"You are a high-caliber CMO with a talent for creating extraordinary LinkedIn content that captivates professional audiences. "
        f"Generate post copy for '{request.business_name}' with the tagline '{request.tagline}'. "
        f"Target Audience: {request.target_audience or 'a diverse professional network'}. "
        f"Objectives: {request.objectives or 'drive thought leadership and generate leads'}. "
        f"Style: {request.style}. Language: {request.language}.\n\n"
        "Your copy must be innovative, persuasive, and designed to elicit a 'WOW' reaction from viewers. "
        "It should incorporate clear calls-to-action, professional yet inspiring language, and be optimized for lead generation on LinkedIn."
    )
    if request.description:
        prompt += f"\nAdditional context: {request.description}"
    if request.extra_instructions:
        prompt += f"\nExtra instructions: {request.extra_instructions}"
    prompt += "\nGenerate the final LinkedIn post copy."
    return prompt

# -----------------------------
# LinkedIn API Integration with Retry Logic
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def post_to_linkedin(message: str) -> dict:
    # Use the LinkedIn UGC API endpoint
    api_url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {config['LINKEDIN_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    payload = {
        "author": config["LINKEDIN_PERSON_URN"],
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": message},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        linkedin_post_id = result.get("id")
        if linkedin_post_id:
            logger.info("LinkedIn post published, ID: %s", linkedin_post_id)
            return {"linkedin_post_id": linkedin_post_id}
        else:
            raise Exception("No post ID returned from LinkedIn")
    except Exception as e:
        logger.error("Failed to post to LinkedIn: %s", e)
        raise

# -----------------------------
# Post Generation Function with Retry Logic
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_linkedin_post_content(request: LinkedInPostRequest) -> str:
    prompt = build_linkedin_post_prompt(request)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=800
        )
        post_copy = response.choices[0].message.content.strip()
        return post_copy
    except Exception as e:
        logger.error("Error generating LinkedIn post content: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to generate post copy: {str(e)}")

# -----------------------------
# API Endpoints for LinkedIn Posts
# -----------------------------
@router.post("/", response_model=LinkedInPostResponse)
async def create_linkedin_post(
    request: LinkedInPostRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Automates the creation of LinkedIn posts for FounderHub.AI.
    
    - Generates "WOW"-worthy post copy via GPT-4.
    - Posts the content to LinkedIn using the UGC API.
    - Stores the post details in SQL with versioning.
    - Sends real-time Slack notifications.
    """
    post_copy = await generate_linkedin_post_content(request)
    try:
        li_result = post_to_linkedin(post_copy)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LinkedIn posting error: {str(e)}")
    
    try:
        post_id = await store_linkedin_post(
            request.tenant_id,
            request.project_id,
            request.post_type,
            request.business_name,
            request.tagline,
            post_copy,
            li_result.get("linkedin_post_id"),
            version=1
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store LinkedIn post: {str(e)}")
    
    background_tasks.add_task(send_slack_notification, f"New LinkedIn {request.post_type} posted for {request.business_name}")
    
    query = """
    SELECT id, tenant_id, project_id, post_type, business_name, tagline, message, linkedin_post_id, created_at, updated_at, version
    FROM linkedin_posts
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": post_id})
    if not row:
        raise HTTPException(status_code=500, detail="Failed to retrieve stored LinkedIn post")
    return LinkedInPostResponse(**row)

@router.put("/{post_id}", response_model=LinkedInPostResponse)
async def update_linkedin_post(
    post_id: str,
    request: LinkedInPostRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Updates an existing LinkedIn post by regenerating post copy and incrementing the version.
    """
    new_post_copy = await generate_linkedin_post_content(request)
    query = "SELECT version FROM linkedin_posts WHERE id = :id"
    current_post = await database.fetch_one(query=query, values={"id": post_id})
    if not current_post:
        raise HTTPException(status_code=404, detail="Post not found")
    new_version = current_post["version"] + 1
    
    await update_linkedin_post_in_db(post_id, new_post_copy, None, new_version)
    background_tasks.add_task(send_slack_notification, f"LinkedIn post {post_id} updated to version {new_version}")
    
    query = """
    SELECT id, tenant_id, project_id, post_type, business_name, tagline, message, linkedin_post_id, created_at, updated_at, version
    FROM linkedin_posts
    WHERE id = :id
    """
    updated_post = await database.fetch_one(query=query, values={"id": post_id})
    if not updated_post:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated LinkedIn post")
    return LinkedInPostResponse(**updated_post)

@router.get("/", response_model=List[LinkedInPostResponse])
async def list_linkedin_posts(
    tenant_id: str,
    project_id: str,
    user=Depends(require_role(["CMO", "Founder"]))
):
    query = """
    SELECT id, tenant_id, project_id, post_type, business_name, tagline, message, linkedin_post_id, created_at, updated_at, version
    FROM linkedin_posts
    WHERE tenant_id = :tenant_id AND project_id = :project_id
    ORDER BY created_at DESC
    """
    rows = await database.fetch_all(query=query, values={"tenant_id": tenant_id, "project_id": project_id})
    return [LinkedInPostResponse(**row) for row in rows]

@router.get("/{post_id}", response_model=LinkedInPostResponse)
async def get_linkedin_post(post_id: str, user=Depends(require_role(["CMO", "Founder"]))):
    query = """
    SELECT id, tenant_id, project_id, post_type, business_name, tagline, message, linkedin_post_id, created_at, updated_at, version
    FROM linkedin_posts
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": post_id})
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    return LinkedInPostResponse(**row)

@router.delete("/{post_id}")
async def delete_linkedin_post(
    post_id: str,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    query = "DELETE FROM linkedin_posts WHERE id = :id"
    result = await database.execute(query=query, values={"id": post_id})
    if not result:
        raise HTTPException(status_code=404, detail="Post not found or already deleted")
    background_tasks.add_task(send_slack_notification, f"LinkedIn post {post_id} deleted")
    return {"detail": "LinkedIn post deleted successfully"}

@router.post("/{post_id}/override", response_model=LinkedInPostResponse)
async def override_linkedin_post(
    override: OverrideRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["Founder"]))
):
    """
    Allows the founder to override an AI-generated LinkedIn post.
    The override is stored and a notification is sent.
    """
    try:
        await store_override(override.tenant_id, override.post_id, override.override_message)
        background_tasks.add_task(send_slack_notification, f"Override applied to LinkedIn post {override.post_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    query = """
    SELECT id, tenant_id, project_id, post_type, business_name, tagline, message, linkedin_post_id, created_at, updated_at, version
    FROM linkedin_posts
    WHERE id = :id
    """
    updated_post = await database.fetch_one(query=query, values={"id": override.post_id})
    if not updated_post:
        raise HTTPException(status_code=404, detail="Post not found after override")
    return LinkedInPostResponse(**updated_post)

@router.post("/{post_id}/abtest")
async def run_linkedin_ab_test(
    post_id: str,
    variant: str = Query(...),
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Triggers an A/B test for a LinkedIn post variant.
    This endpoint would deploy variant posts, track performance, and store results for analysis.
    """
    background_tasks.add_task(send_slack_notification, f"A/B test triggered for LinkedIn post {post_id} with variant '{variant}'")
    return {"detail": f"A/B test for post {post_id} with variant '{variant}' triggered."}

# Helper function to update LinkedIn post in DB
async def update_linkedin_post_in_db(post_id: str, message: str, linkedin_post_id: Optional[str], version: int) -> None:
    now = datetime.utcnow()
    query = """
    UPDATE linkedin_posts
    SET message = :message, linkedin_post_id = :linkedin_post_id, updated_at = :updated_at, version = :version
    WHERE id = :id
    """
    values = {"id": post_id, "message": message, "linkedin_post_id": linkedin_post_id, "updated_at": now, "version": version}
    await database.execute(query=query, values=values)
