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

# Load environment variables and initialize the asynchronous database connection.
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
database = Database(DATABASE_URL)

# Global configuration dictionary loaded from DB (assume this is done on startup).
# For this module, we expect keys: "OPENAI_API_KEY", "GOOGLE_ADS_API_TOKEN", "SLACK_WEBHOOK_URL"
config: Dict[str, str] = {}  # Filled by load_config() at startup.

async def get_config_value(key: str) -> str:
    query = "SELECT config_value FROM system_config WHERE config_key = :key"
    row = await database.fetch_one(query=query, values={"key": key})
    if not row:
        raise RuntimeError(f"Configuration key '{key}' not found in DB")
    return row["config_value"]

async def load_config():
    keys = ["OPENAI_API_KEY", "GOOGLE_ADS_API_TOKEN", "SLACK_WEBHOOK_URL"]
    for key in keys:
        config[key] = await get_config_value(key)
    openai.api_key = config["OPENAI_API_KEY"]
    logging.info("Configuration loaded from DB.")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google/ads", tags=["Google Ads"])

# -----------------------------
# Authentication & RBAC
# -----------------------------
def get_current_user():
    # Replace with your production authentication logic.
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
# Pydantic Models for Google Ads
# -----------------------------
class GoogleAdRequest(BaseModel):
    tenant_id: str
    project_id: str
    ad_type: str = Field(..., description="e.g., 'search', 'display', 'video'")
    business_name: str
    tagline: str
    target_audience: Optional[str] = Field(None, description="Target audience for the ad")
    objectives: Optional[str] = Field(None, description="Marketing objectives (lead generation, brand awareness, etc.)")
    description: Optional[str] = Field("", description="Additional creative details")
    style: Optional[str] = Field("modern", description="Tone and style (energetic, professional, playful, etc.)")
    language: Optional[str] = Field("en", description="Language code (e.g., 'en', 'es', 'fr')")
    extra_instructions: Optional[str] = Field("", description="Extra instructions for the ad copy")

class GoogleAdResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    ad_type: str
    business_name: str
    tagline: str
    message: str
    google_ad_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    version: int

class OverrideRequest(BaseModel):
    tenant_id: str
    ad_id: str
    override_message: str

# -----------------------------
# Database Helper Functions (Async)
# -----------------------------
async def store_google_ad(
    tenant_id: str,
    project_id: str,
    ad_type: str,
    business_name: str,
    tagline: str,
    message: str,
    google_ad_id: Optional[str],
    version: int = 1
) -> str:
    ad_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO google_ads (id, tenant_id, project_id, ad_type, business_name, tagline, message, google_ad_id, created_at, updated_at, version)
    VALUES (:id, :tenant_id, :project_id, :ad_type, :business_name, :tagline, :message, :google_ad_id, :created_at, :updated_at, :version)
    """
    values = {
        "id": ad_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "ad_type": ad_type,
        "business_name": business_name,
        "tagline": tagline,
        "message": message,
        "google_ad_id": google_ad_id,
        "created_at": now,
        "updated_at": now,
        "version": version,
    }
    await database.execute(query=query, values=values)
    return ad_id

async def update_google_ad_in_db(ad_id: str, message: str, google_ad_id: Optional[str], version: int) -> None:
    now = datetime.utcnow()
    query = """
    UPDATE google_ads
    SET message = :message, google_ad_id = :google_ad_id, updated_at = :updated_at, version = :version
    WHERE id = :id
    """
    values = {"id": ad_id, "message": message, "google_ad_id": google_ad_id, "updated_at": now, "version": version}
    await database.execute(query=query, values=values)

async def store_override(tenant_id: str, ad_id: str, override_message: str) -> str:
    override_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO overrides (id, tenant_id, design_id, override_message, created_at)
    VALUES (:id, :tenant_id, :design_id, :override_message, :created_at)
    """
    values = {
        "id": override_id,
        "tenant_id": tenant_id,
        "design_id": ad_id,
        "override_message": override_message,
        "created_at": now,
    }
    await database.execute(query=query, values=values)
    return override_id

# -----------------------------
# Advanced Prompt Builder for Google Ads
# -----------------------------
def build_google_ad_prompt(request: GoogleAdRequest) -> str:
    prompt = (
        f"You are an elite digital marketing strategist tasked with creating an extraordinary Google Ads campaign for "
        f"'{request.business_name}' with the tagline '{request.tagline}'. "
        f"Target Audience: {request.target_audience or 'a broad audience'}. "
        f"Objectives: {request.objectives or 'to drive high-quality leads and maximize conversions'}. "
        f"Style: {request.style}. Language: {request.language}.\n\n"
        "Your ad copy must be innovative, highly persuasive, and capable of generating 'WOW' responses. "
        "Include a strong call-to-action, emotional triggers, and clear messaging that surpasses human expectations. "
        "Optimize for both engagement and conversion. "
    )
    if request.description:
        prompt += f"\nAdditional context: {request.description}"
    if request.extra_instructions:
        prompt += f"\nExtra instructions: {request.extra_instructions}"
    prompt += "\nGenerate the final Google Ads copy."
    return prompt

# -----------------------------
# Google Ads API Integration with Retry Logic
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def post_to_google_ads(message: str) -> dict:
    # Hypothetical Google Ads API endpoint; adjust as needed.
    api_url = "https://api.googleads.com/v1/ads"
    payload = {
        "message": message,
        "access_token": config["GOOGLE_ADS_API_TOKEN"]
    }
    try:
        response = requests.post(api_url, data=payload)
        response.raise_for_status()
        result = response.json()
        google_ad_id = result.get("id")
        if google_ad_id:
            logger.info("Google ad posted, ID: %s", google_ad_id)
            return {"google_ad_id": google_ad_id}
        else:
            raise Exception("No ad ID returned from Google Ads API")
    except Exception as e:
        logger.error("Failed to post to Google Ads: %s", e)
        raise

# -----------------------------
# Ad Copy Generation Function with Retry Logic
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_google_ad_content(request: GoogleAdRequest) -> str:
    prompt = build_google_ad_prompt(request)
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
        logger.error("Error generating Google ad content: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to generate ad copy: {str(e)}")

# -----------------------------
# API Endpoints for Google Ads
# -----------------------------
@router.post("/", response_model=GoogleAdResponse)
async def create_google_ad(
    request: GoogleAdRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Automates the creation of Google Ads campaigns.
    
    - Generates a high-impact ad copy via GPT-4.
    - Posts the ad to Google Ads using a hypothetical API.
    - Stores ad details in SQL with versioning.
    - Sends real-time Slack notifications.
    """
    ad_copy = await generate_google_ad_content(request)
    try:
        ga_result = post_to_google_ads(ad_copy)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Ads posting error: {str(e)}")
    
    try:
        ad_id = await store_google_ad(
            request.tenant_id,
            request.project_id,
            request.ad_type,
            request.business_name,
            request.tagline,
            ad_copy,
            ga_result.get("google_ad_id"),
            version=1
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store Google ad: {str(e)}")
    
    background_tasks.add_task(send_slack_notification, f"New Google ad posted for {request.business_name}")
    
    query = """
    SELECT id, tenant_id, project_id, ad_type, business_name, tagline, message, google_ad_id, created_at, updated_at, version
    FROM google_ads
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": ad_id})
    if not row:
        raise HTTPException(status_code=500, detail="Failed to retrieve stored Google ad")
    return GoogleAdResponse(**row)

@router.put("/{ad_id}", response_model=GoogleAdResponse)
async def update_google_ad(
    ad_id: str,
    request: GoogleAdRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Updates an existing Google ad by regenerating ad copy and incrementing the version.
    """
    new_ad_copy = await generate_google_ad_content(request)
    query = "SELECT version FROM google_ads WHERE id = :id"
    current_ad = await database.fetch_one(query=query, values={"id": ad_id})
    if not current_ad:
        raise HTTPException(status_code=404, detail="Ad not found")
    new_version = current_ad["version"] + 1
    
    await update_google_ad_in_db(ad_id, new_ad_copy, None, new_version)
    background_tasks.add_task(send_slack_notification, f"Google ad {ad_id} updated to version {new_version}")
    
    query = """
    SELECT id, tenant_id, project_id, ad_type, business_name, tagline, message, google_ad_id, created_at, updated_at, version
    FROM google_ads
    WHERE id = :id
    """
    updated_ad = await database.fetch_one(query=query, values={"id": ad_id})
    if not updated_ad:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated Google ad")
    return GoogleAdResponse(**updated_ad)

@router.get("/", response_model=List[GoogleAdResponse])
async def list_google_ads(
    tenant_id: str,
    project_id: str,
    user=Depends(require_role(["CMO", "Founder"]))
):
    query = """
    SELECT id, tenant_id, project_id, ad_type, business_name, tagline, message, google_ad_id, created_at, updated_at, version
    FROM google_ads
    WHERE tenant_id = :tenant_id AND project_id = :project_id
    ORDER BY created_at DESC
    """
    rows = await database.fetch_all(query=query, values={"tenant_id": tenant_id, "project_id": project_id})
    return [GoogleAdResponse(**row) for row in rows]

@router.get("/{ad_id}", response_model=GoogleAdResponse)
async def get_google_ad(ad_id: str, user=Depends(require_role(["CMO", "Founder"]))):
    query = """
    SELECT id, tenant_id, project_id, ad_type, business_name, tagline, message, google_ad_id, created_at, updated_at, version
    FROM google_ads
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": ad_id})
    if not row:
        raise HTTPException(status_code=404, detail="Ad not found")
    return GoogleAdResponse(**row)

@router.delete("/{ad_id}")
async def delete_google_ad(
    ad_id: str,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    query = "DELETE FROM google_ads WHERE id = :id"
    result = await database.execute(query=query, values={"id": ad_id})
    if not result:
        raise HTTPException(status_code=404, detail="Ad not found or already deleted")
    background_tasks.add_task(send_slack_notification, f"Google ad {ad_id} deleted")
    return {"detail": "Google ad deleted successfully"}

@router.post("/{ad_id}/override", response_model=GoogleAdResponse)
async def override_google_ad(
    override: OverrideRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["Founder"]))
):
    """
    Allows the founder to override an AI-generated Google ad.
    The override is stored in the database and a notification is sent.
    """
    try:
        await store_override(override.tenant_id, override.ad_id, override.override_message)
        background_tasks.add_task(send_slack_notification, f"Override applied to Google ad {override.ad_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    query = """
    SELECT id, tenant_id, project_id, ad_type, business_name, tagline, message, google_ad_id, created_at, updated_at, version
    FROM google_ads
    WHERE id = :id
    """
    updated_ad = await database.fetch_one(query=query, values={"id": override.ad_id})
    if not updated_ad:
        raise HTTPException(status_code=404, detail="Ad not found after override")
    return GoogleAdResponse(**updated_ad)

@router.get("/{ad_id}/metrics", response_model=Dict[str, float])
async def fetch_google_ad_metrics(ad_id: str, user=Depends(require_role(["CMO", "Founder"]))):
    """
    Retrieves performance metrics for a given Google ad.
    In production, integrate with the Google Ads API to fetch real metrics.
    """
    # Hypothetical API call simulation:
    try:
        # Simulate an API call to Google Ads Insights.
        metrics = {
            "impressions": 2000.0,
            "clicks": 80.0,
            "ctr": 4.0,  # 4%
            "cost": 150.0,
        }
        return metrics
    except Exception as e:
        logger.error("Error fetching Google ad metrics: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch ad metrics: {str(e)}")

@router.post("/{ad_id}/optimize", response_model=GoogleAdResponse)
async def optimize_google_ad(
    ad_id: str,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Analyzes the performance metrics of a Google ad and auto-optimizes the ad copy if KPIs fall below thresholds.
    """
    ctr_threshold = 3.0  # Example CTR threshold (3%)
    query = """
    SELECT id, tenant_id, project_id, ad_type, business_name, tagline, message, google_ad_id, created_at, updated_at, version
    FROM google_ads
    WHERE id = :id
    """
    current_ad = await database.fetch_one(query=query, values={"id": ad_id})
    if not current_ad:
        raise HTTPException(status_code=404, detail="Ad not found for optimization")
    
    metrics = await fetch_google_ad_metrics(ad_id, user)
    if metrics.get("ctr", 0) < ctr_threshold:
        optimization_instructions = "Optimize for higher CTR by adding emotional triggers and a stronger call-to-action."
        new_request = GoogleAdRequest(
            tenant_id=current_ad["tenant_id"],
            project_id=current_ad["project_id"],
            ad_type=current_ad["ad_type"],
            business_name="",
            tagline="",
            target_audience="",
            objectives="",
            description=optimization_instructions,
            style="modern",
            language="en",
            extra_instructions=""
        )
        new_ad_copy = await generate_google_ad_content(new_request)
        new_version = current_ad["version"] + 1
        await update_google_ad_in_db(ad_id, new_ad_copy, None, new_version)
        background_tasks.add_task(send_slack_notification, f"Google ad {ad_id} auto-optimized to version {new_version}")
        
        query = """
        SELECT id, tenant_id, project_id, ad_type, business_name, tagline, message, google_ad_id, created_at, updated_at, version
        FROM google_ads
        WHERE id = :id
        """
        updated_ad = await database.fetch_one(query=query, values={"id": ad_id})
        if not updated_ad:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated Google ad")
        return GoogleAdResponse(**updated_ad)
    else:
        return {"detail": f"Ad CTR ({metrics.get('ctr')}%) meets threshold. No optimization needed."}

@router.post("/{ad_id}/abtest")
async def run_google_ab_test(
    ad_id: str,
    variant: str = Query(...),
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Triggers an A/B test for a Google ad variant.
    This endpoint would deploy the variant, track performance, and store results for analysis.
    """
    background_tasks.add_task(send_slack_notification, f"A/B test triggered for Google ad {ad_id} with variant '{variant}'")
    return {"detail": f"A/B test for ad {ad_id} with variant '{variant}' triggered."}
