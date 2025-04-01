import os
import uuid
import logging
from datetime import datetime, date
from typing import List, Optional, Dict

import openai
import requests
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, Field
from databases import Database
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

# Load environment variables and initialize the async database connection.
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
database = Database(DATABASE_URL)

# Global configuration dictionary loaded from DB.
# The system_config table must contain keys: "OPENAI_API_KEY", "SLACK_WEBHOOK_URL"
config: Dict[str, str] = {}

async def get_config_value(key: str) -> str:
    query = "SELECT config_value FROM system_config WHERE config_key = :key"
    row = await database.fetch_one(query=query, values={"key": key})
    if not row:
        raise RuntimeError(f"Configuration key '{key}' not found in DB")
    return row["config_value"]

async def load_config():
    keys = ["OPENAI_API_KEY", "SLACK_WEBHOOK_URL"]
    for key in keys:
        config[key] = await get_config_value(key)
    openai.api_key = config["OPENAI_API_KEY"]
    logging.info("Configuration loaded from DB.")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/free-advertising", tags=["Free Advertising"])

# -----------------------------
# Authentication & RBAC (Production-Ready)
# -----------------------------
def get_current_user():
    # Replace this stub with your real authentication mechanism.
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
# Pydantic Models for Free Advertising Plans
# -----------------------------
class FreeAdvertisingRequest(BaseModel):
    tenant_id: str
    project_id: str
    business_name: str
    industry: Optional[str] = Field(None, description="Industry of the business (e.g., 'retail', 'tech', 'service')")
    target_audience: Optional[str] = Field(None, description="Target audience description")
    additional_context: Optional[str] = Field("", description="Additional context or challenges the business faces")
    language: Optional[str] = Field("en", description="Language code (e.g., 'en', 'es', 'fr')")

class FreeAdvertisingResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    business_name: str
    industry: Optional[str]
    target_audience: Optional[str]
    advice: str
    created_at: datetime
    updated_at: datetime
    version: int

# -----------------------------
# Database Helper Functions for Free Advertising Plans (Async)
# -----------------------------
async def store_advertising_plan(
    tenant_id: str,
    project_id: str,
    business_name: str,
    industry: Optional[str],
    target_audience: Optional[str],
    advice: str,
    version: int = 1
) -> str:
    plan_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO free_advertising_plans 
    (id, tenant_id, project_id, business_name, industry, target_audience, advice, created_at, updated_at, version)
    VALUES (:id, :tenant_id, :project_id, :business_name, :industry, :target_audience, :advice, :created_at, :updated_at, :version)
    """
    values = {
        "id": plan_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "business_name": business_name,
        "industry": industry,
        "target_audience": target_audience,
        "advice": advice,
        "created_at": now,
        "updated_at": now,
        "version": version,
    }
    await database.execute(query=query, values=values)
    return plan_id

# -----------------------------
# Advanced Prompt Builder for Free Advertising Plans
# -----------------------------
def build_free_advertising_prompt(request: FreeAdvertisingRequest) -> str:
    prompt = (
        f"You are a top-tier marketing strategist with a passion for helping small businesses grow using cost-effective, free advertising methods. "
        f"Generate a comprehensive free advertising strategy for the business '{request.business_name}' operating in the '{request.industry or 'general'}' industry. "
        f"Target Audience: {request.target_audience or 'a broad audience'}. "
        "Your strategy should cover every aspect of low-cost marketing, including but not limited to:\n"
        "- Identifying available grants and government funding opportunities\n"
        "- Creating compelling press releases that attract media attention\n"
        "- Email outreach strategies to radio and TV stations for free publicity\n"
        "- Leveraging free online advertising channels (social media, content marketing, SEO, etc.)\n"
        "- Innovative guerrilla marketing tactics\n"
        "- Partnership opportunities with local influencers and community organizations\n"
        "- Tools and resources for automating these processes\n"
        "Include actionable advice, resource links (e.g., to government grant portals, free press release distribution services), and clear next steps. "
        "Ensure your response is extremely detailed, innovative, and leaves the reader saying 'WOW'—this strategy must be better than any human effort.\n"
    )
    if request.additional_context:
        prompt += f"\nAdditional context: {request.additional_context}"
    prompt += "\nProvide the final free advertising strategy."
    return prompt

# -----------------------------
# Free Advertising Strategy Generation Function with Retry Logic
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_free_advertising_strategy(request: FreeAdvertisingRequest) -> str:
    prompt = build_free_advertising_prompt(request)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75,
            max_tokens=1500
        )
        advice = response.choices[0].message.content.strip()
        return advice
    except Exception as e:
        logger.error("Error generating free advertising strategy: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to generate strategy: {str(e)}")

# -----------------------------
# API Endpoints for Free Advertising Strategies
# -----------------------------
@router.post("/", response_model=FreeAdvertisingResponse)
async def create_free_advertising_plan(
    request: FreeAdvertisingRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    """
    Generates a comprehensive free advertising strategy for a small business.
    
    The strategy covers grants, press releases, media outreach (e.g., radio/TV), online free advertising, and guerrilla marketing.
    It includes actionable steps, resource links, and recommendations.
    
    The generated strategy is stored in the database with versioning, and a Slack notification is sent.
    """
    advice = await generate_free_advertising_strategy(request)
    try:
        plan_id = await store_advertising_plan(
            request.tenant_id,
            request.project_id,
            request.business_name,
            request.industry,
            request.target_audience,
            advice,
            version=1
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store advertising strategy: {str(e)}")
    
    background_tasks.add_task(send_slack_notification, f"New free advertising strategy created for {request.business_name}")
    
    query = """
    SELECT id, tenant_id, project_id, business_name, industry, target_audience, advice, created_at, updated_at, version
    FROM free_advertising_plans
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": plan_id})
    if not row:
        raise HTTPException(status_code=500, detail="Failed to retrieve stored advertising strategy")
    return FreeAdvertisingResponse(**row)

@router.get("/", response_model=List[FreeAdvertisingResponse])
async def list_free_advertising_plans(
    tenant_id: str,
    project_id: str,
    user=Depends(require_role(["CMO", "Founder"]))
):
    query = """
    SELECT id, tenant_id, project_id, business_name, industry, target_audience, advice, created_at, updated_at, version
    FROM free_advertising_plans
    WHERE tenant_id = :tenant_id AND project_id = :project_id
    ORDER BY created_at DESC
    """
    rows = await database.fetch_all(query=query, values={"tenant_id": tenant_id, "project_id": project_id})
    return [FreeAdvertisingResponse(**row) for row in rows]

@router.get("/{plan_id}", response_model=FreeAdvertisingResponse)
async def get_free_advertising_plan(plan_id: str, user=Depends(require_role(["CMO", "Founder"]))):
    query = """
    SELECT id, tenant_id, project_id, business_name, industry, target_audience, advice, created_at, updated_at, version
    FROM free_advertising_plans
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": plan_id})
    if not row:
        raise HTTPException(status_code=404, detail="Advertising strategy not found")
    return FreeAdvertisingResponse(**row)
