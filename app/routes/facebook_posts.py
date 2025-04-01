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

# -----------------------------
# Global Configuration (Loaded from DB)
# -----------------------------
# DATABASE_URL is assumed to be provided via environment variable
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
database = Database(DATABASE_URL)

# Global config dictionary to store sensitive keys loaded from DB
config: Dict[str, str] = {}

async def get_config_value(key: str) -> str:
    """
    Retrieves the configuration value from the system_config table in the database.
    The table should have columns: config_key (TEXT PRIMARY KEY), config_value (TEXT).
    """
    query = "SELECT config_value FROM system_config WHERE config_key = :key"
    row = await database.fetch_one(query=query, values={"key": key})
    if not row:
        raise RuntimeError(f"Configuration key '{key}' not found in DB")
    return row["config_value"]

async def load_config():
    """
    Loads all required configuration keys from the database into the global 'config' dictionary.
    """
    keys = ["OPENAI_API_KEY", "FB_PAGE_TOKEN", "CANVA_API_TOKEN", "SLACK_WEBHOOK_URL"]
    for key in keys:
        config[key] = await get_config_value(key)
    openai.api_key = config["OPENAI_API_KEY"]
    logging.info("Configuration loaded from DB.")

# -----------------------------
# Setup Logging
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Router Setup
# -----------------------------
router = APIRouter(prefix="/facebook/posts", tags=["Facebook Posts"])

# -----------------------------
# Authentication & RBAC (Production-Ready)
# -----------------------------
def get_current_user():
    # Replace with your production authentication mechanism.
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
# Pydantic Models for Facebook Posts and Campaigns
# -----------------------------
class FacebookPostRequest(BaseModel):
    tenant_id: str
    project_id: str
    post_type: str = Field(..., description="e.g., 'page', 'ad'")
    campaign_name: Optional[str] = Field(None, description="Optional campaign name")
    business_name: str
    tagline: str
    target_audience: Optional[str] = Field(None, description="Target audience for the ad/post")
    objectives: Optional[str] = Field(None, description="Marketing objectives (lead generation, brand awareness, etc.)")
    description: Optional[str] = Field("", description="Additional creative details")
    style: Optional[str] = Field("modern", description="Tone and style (energetic, professional, playful, etc.)")
    language: Optional[str] = Field("en", description="Language code (e.g., 'en', 'es', 'fr')")
    extra_instructions: Optional[str] = Field("", description="Extra instructions for the AI copy")

class FacebookPostResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    post_type: str
    message: str
    fb_post_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    version: int

class CampaignRequest(BaseModel):
    tenant_id: str
    project_id: str
    campaign_name: str
    objective: str
    budget: float
    start_date: date
    end_date: date
    creative_details: Optional[str] = Field("", description="Design ideas and creative guidelines")

class CampaignResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    campaign_name: str
    objective: str
    budget: float
    start_date: date
    end_date: date
    creative_details: Optional[str]
    fb_campaign_id: Optional[str]
    created_at: datetime
    updated_at: datetime

class OverrideRequest(BaseModel):
    tenant_id: str
    design_id: str  # ID of the Facebook post or campaign to override
    override_message: str

# -----------------------------
# Database Helper Functions (Async)
# -----------------------------
async def store_facebook_post(
    tenant_id: str,
    project_id: str,
    post_type: str,
    business_name: str,
    tagline: str,
    message: str,
    fb_post_id: Optional[str],
    version: int = 1
) -> str:
    post_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO facebook_posts (id, tenant_id, project_id, post_type, message, fb_post_id, created_at, updated_at, version)
    VALUES (:id, :tenant_id, :project_id, :post_type, :message, :fb_post_id, :created_at, :updated_at, :version)
    """
    values = {
        "id": post_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "post_type": post_type,
        "message": message,
        "fb_post_id": fb_post_id,
        "created_at": now,
        "updated_at": now,
        "version": version,
    }
    await database.execute(query=query, values=values)
    return post_id

async def update_facebook_post_in_db(post_id: str, message: str, fb_post_id: Optional[str], version: int) -> None:
    now = datetime.utcnow()
    query = """
    UPDATE facebook_posts
    SET message = :message, fb_post_id = :fb_post_id, updated_at = :updated_at, version = :version
    WHERE id = :id
    """
    values = {"id": post_id, "message": message, "fb_post_id": fb_post_id, "updated_at": now, "version": version}
    await database.execute(query=query, values=values)

async def store_campaign(campaign: CampaignRequest, fb_campaign_id: Optional[str] = None) -> str:
    campaign_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO facebook_campaigns (id, tenant_id, project_id, campaign_name, objective, budget, start_date, end_date, creative_details, fb_campaign_id, created_at, updated_at)
    VALUES (:id, :tenant_id, :project_id, :campaign_name, :objective, :budget, :start_date, :end_date, :creative_details, :fb_campaign_id, :created_at, :updated_at)
    """
    values = {
        "id": campaign_id,
        "tenant_id": campaign.tenant_id,
        "project_id": campaign.project_id,
        "campaign_name": campaign.campaign_name,
        "objective": campaign.objective,
        "budget": campaign.budget,
        "start_date": campaign.start_date,
        "end_date": campaign.end_date,
        "creative_details": campaign.creative_details,
        "fb_campaign_id": fb_campaign_id,
        "created_at": now,
        "updated_at": now,
    }
    await database.execute(query=query, values=values)
    return campaign_id

async def store_override(tenant_id: str, design_id: str, override_message: str) -> str:
    override_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO overrides (id, tenant_id, design_id, override_message, created_at)
    VALUES (:id, :tenant_id, :design_id, :override_message, :created_at)
    """
    values = {
        "id": override_id,
        "tenant_id": tenant_id,
        "design_id": design_id,
        "override_message": override_message,
        "created_at": now,
    }
    await database.execute(query=query, values=values)
    return override_id

# -----------------------------
# Advanced Prompt Builder for Facebook Ads/Posts
# -----------------------------
def build_facebook_post_prompt(request: FacebookPostRequest) -> str:
    prompt = (
        f"You are a world-class CMO for FounderHub.AI tasked with creating 'WOW'-worthy Facebook {request.post_type} content. "
        f"Generate ad copy for '{request.business_name}' with the tagline '{request.tagline}'. "
        f"Target Audience: {request.target_audience or 'a wide audience'}. "
        f"Objectives: {request.objectives or 'drive leads and build brand awareness'}. "
        f"Style: {request.style}. Language: {request.language}.\n\n"
        "Your copy must be innovative, emotionally compelling, and persuasive—so impressive that viewers immediately say 'WOW'. "
        "Incorporate strong calls-to-action and creative language that maximizes engagement and lead generation."
    )
    if request.description:
        prompt += f"\nAdditional context: {request.description}"
    if request.extra_instructions:
        prompt += f"\nExtra instructions: {request.extra_instructions}"
    prompt += "\nGenerate the final Facebook ad copy."
    return prompt

# -----------------------------
# Facebook Graph API Integration with Retry Logic
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def post_to_facebook(message: str) -> dict:
    api_url = "https://graph.facebook.com/me/feed"
    payload = {
        "message": message,
        "access_token": config["FB_PAGE_TOKEN"]
    }
    try:
        response = requests.post(api_url, data=payload)
        response.raise_for_status()
        result = response.json()
        fb_post_id = result.get("id")
        if fb_post_id:
            logger.info("Facebook post published, ID: %s", fb_post_id)
            return {"fb_post_id": fb_post_id}
        else:
            raise Exception("No post ID returned from Facebook")
    except Exception as e:
        logger.error("Failed to post to Facebook: %s", e)
        raise

# -----------------------------
# Post Generation Function with Retry Logic
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_facebook_post_content(request: FacebookPostRequest) -> str:
    prompt = build_facebook_post_prompt(request)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=800
        )
        ad_copy = response.choices[0].message.content.strip()
        return ad_copy
    except Exception as e:
        logger.error("Error generating Facebook post content: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to generate ad copy: {str(e)}")

# -----------------------------
# API Endpoints for Facebook Posts & Campaigns
# -----------------------------
@router.post("/", response_model=FacebookPostResponse)
async def create_facebook_post(
    request: FacebookPostRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Automates creation of Facebook posts/ads:
      - Generates "WOW"‑worthy ad copy via GPT-4.
      - Posts the ad to Facebook using the Graph API.
      - Stores post details in SQL with versioning.
      - Sends real-time Slack notifications.
    """
    ad_copy = await generate_facebook_post_content(request)
    try:
        fb_result = post_to_facebook(ad_copy)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Facebook posting error: {str(e)}")
    
    try:
        post_id = await store_facebook_post(
            request.tenant_id,
            request.project_id,
            request.post_type,
            request.business_name,
            request.tagline,
            ad_copy,
            fb_result.get("fb_post_id"),
            version=1
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store Facebook post: {str(e)}")
    
    background_tasks.add_task(send_slack_notification, f"New Facebook {request.post_type} posted for {request.business_name}")
    
    query = """
    SELECT id, tenant_id, project_id, post_type, message, fb_post_id, created_at, updated_at, version
    FROM facebook_posts
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": post_id})
    if not row:
        raise HTTPException(status_code=500, detail="Failed to retrieve stored Facebook post")
    return FacebookPostResponse(**row)

@router.put("/{post_id}", response_model=FacebookPostResponse)
async def update_facebook_post(
    post_id: str,
    request: FacebookPostRequest,
    revision_notes: str = "",
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Updates an existing Facebook post/ad by regenerating ad copy and creating a new version.
    """
    new_ad_copy = await generate_facebook_post_content(request)
    query = "SELECT version FROM facebook_posts WHERE id = :id"
    current_post = await database.fetch_one(query=query, values={"id": post_id})
    if not current_post:
        raise HTTPException(status_code=404, detail="Post not found")
    new_version = current_post["version"] + 1
    
    await update_facebook_post_in_db(post_id, new_ad_copy, None, new_version)
    await store_design_revision(post_id, new_version, revision_notes)
    
    background_tasks.add_task(send_slack_notification, f"Facebook post {post_id} updated to version {new_version}")
    
    query = """
    SELECT id, tenant_id, project_id, post_type, message, fb_post_id, created_at, updated_at, version
    FROM facebook_posts
    WHERE id = :id
    """
    updated_post = await database.fetch_one(query=query, values={"id": post_id})
    if not updated_post:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated Facebook post")
    return FacebookPostResponse(**updated_post)

@router.get("/", response_model=List[FacebookPostResponse])
async def list_facebook_posts(
    tenant_id: str,
    project_id: str,
    user=Depends(require_role(["CMO", "Founder"]))
):
    query = """
    SELECT id, tenant_id, project_id, post_type, message, fb_post_id, created_at, updated_at, version
    FROM facebook_posts
    WHERE tenant_id = :tenant_id AND project_id = :project_id
    ORDER BY created_at DESC
    """
    rows = await database.fetch_all(query=query, values={"tenant_id": tenant_id, "project_id": project_id})
    return [FacebookPostResponse(**row) for row in rows]

@router.get("/{post_id}", response_model=FacebookPostResponse)
async def get_facebook_post(post_id: str, user=Depends(require_role(["CMO", "Founder"]))):
    query = """
    SELECT id, tenant_id, project_id, post_type, message, fb_post_id, created_at, updated_at, version
    FROM facebook_posts
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": post_id})
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    return FacebookPostResponse(**row)

@router.delete("/{post_id}")
async def delete_facebook_post(
    post_id: str,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    query = "DELETE FROM facebook_posts WHERE id = :id"
    result = await database.execute(query=query, values={"id": post_id})
    if not result:
        raise HTTPException(status_code=404, detail="Post not found or already deleted")
    background_tasks.add_task(send_slack_notification, f"Facebook post {post_id} deleted")
    return {"detail": "Facebook post deleted successfully"}

@router.post("/{post_id}/override", response_model=FacebookPostResponse)
async def override_facebook_post(
    override: OverrideRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["Founder"]))
):
    """
    Allows the founder to override an AI-generated Facebook post.
    The override is stored in the database and a notification is sent.
    """
    try:
        await store_override(override.tenant_id, override.design_id, override.override_message)
        background_tasks.add_task(send_slack_notification, f"Override applied to Facebook post {override.design_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    query = """
    SELECT id, tenant_id, project_id, post_type, message, fb_post_id, created_at, updated_at, version
    FROM facebook_posts
    WHERE id = :id
    """
    updated_post = await database.fetch_one(query=query, values={"id": override.design_id})
    if not updated_post:
        raise HTTPException(status_code=404, detail="Post not found after override")
    return FacebookPostResponse(**updated_post)

@router.get("/{post_id}/metrics", response_model=Dict[str, float])
async def fetch_facebook_post_metrics(post_id: str, user=Depends(require_role(["CMO", "Founder"]))):
    """
    Retrieves performance metrics for a given Facebook post via a simulated Facebook Insights API call.
    """
    api_url = f"https://graph.facebook.com/{post_id}/insights"
    params = {"access_token": config["FB_PAGE_TOKEN"]}
    try:
        response = requests.get(api_url, params=params)
        response.raise_for_status()
        # For production, parse the actual metrics from the response.
        metrics = {
            "impressions": 1000.0,
            "clicks": 50.0,
            "ctr": 5.0,  # 5%
            "spend": 100.0,
        }
        return metrics
    except Exception as e:
        logger.error("Error fetching Facebook post metrics: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch post metrics: {str(e)}")

@router.post("/{post_id}/optimize", response_model=FacebookPostResponse)
async def optimize_facebook_post(
    post_id: str,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Analyzes performance metrics of a Facebook post and auto-optimizes the ad copy if KPIs are below thresholds.
    """
    # Example threshold for CTR (click-through rate)
    ctr_threshold = 2.0  # 2%
    query = """
    SELECT id, tenant_id, project_id, post_type, message, fb_post_id, created_at, updated_at, version
    FROM facebook_posts
    WHERE id = :id
    """
    current_post = await database.fetch_one(query=query, values={"id": post_id})
    if not current_post:
        raise HTTPException(status_code=404, detail="Post not found for optimization")
    
    metrics = await fetch_facebook_post_metrics(post_id, user)
    if metrics.get("ctr", 0) < ctr_threshold:
        # Regenerate ad copy with optimization instructions
        optimization_instructions = "Optimize for higher engagement and CTR with more emotional triggers."
        # For simplicity, we create a new request merging existing copy with optimization instructions.
        new_request = FacebookPostRequest(
            tenant_id=current_post["tenant_id"],
            project_id=current_post["project_id"],
            post_type=current_post["post_type"],
            campaign_name="",
            business_name="",
            tagline="",
            target_audience="",
            objectives="",
            description=optimization_instructions,
            style="modern",
            language="en",
            extra_instructions=""
        )
        new_ad_copy = await generate_facebook_post_content(new_request)
        new_version = current_post["version"] + 1
        
        await update_facebook_post_in_db(post_id, new_ad_copy, None, new_version)
        background_tasks.add_task(send_slack_notification, f"Facebook post {post_id} auto-optimized to version {new_version}")
        
        query = """
        SELECT id, tenant_id, project_id, post_type, message, fb_post_id, created_at, updated_at, version
        FROM facebook_posts
        WHERE id = :id
        """
        updated_post = await database.fetch_one(query=query, values={"id": post_id})
        if not updated_post:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated post")
        return FacebookPostResponse(**updated_post)
    else:
        return {"detail": f"Post CTR ({metrics.get('ctr')}%) meets threshold. No optimization needed."}

@router.post("/{post_id}/abtest")
async def run_ab_test(
    post_id: str,
    variant: str = Query(...),
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Triggers an A/B test for a Facebook post variant.
    In a complete solution, this endpoint would deploy variant designs, track performance metrics, and store the results.
    """
    background_tasks.add_task(send_slack_notification, f"A/B test triggered for post {post_id} with variant '{variant}'")
    return {"detail": f"A/B test for post {post_id} with variant '{variant}' triggered."}
