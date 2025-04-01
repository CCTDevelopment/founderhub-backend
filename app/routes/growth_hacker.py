import os
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Dict

import openai
import requests
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

# Global configuration loaded from DB via system_config table.
# Expect keys: "OPENAI_API_KEY", "SLACK_WEBHOOK_URL"
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

router = APIRouter(prefix="/growth-hacker", tags=["Growth Hacker"])

# -----------------------------
# Authentication & RBAC (Production-Ready)
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
# Pydantic Models for Growth Hacks
# -----------------------------
class GrowthHackRequest(BaseModel):
    tenant_id: str
    project_id: str
    business_name: str
    industry: Optional[str] = Field(None, description="Industry of the business")
    target_audience: Optional[str] = Field(None, description="Description of the target audience")
    additional_context: Optional[str] = Field("", description="Additional context or challenges")
    language: Optional[str] = Field("en", description="Language code (e.g., 'en', 'es', 'fr')")

class GrowthHackResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    business_name: str
    industry: Optional[str]
    target_audience: Optional[str]
    strategy: str
    created_at: datetime
    updated_at: datetime
    version: int

# -----------------------------
# Database Helper Functions (Async)
# -----------------------------
async def store_growth_hack(
    tenant_id: str,
    project_id: str,
    business_name: str,
    industry: Optional[str],
    target_audience: Optional[str],
    strategy: str,
    version: int = 1
) -> str:
    hack_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO growth_hacks (id, tenant_id, project_id, business_name, industry, target_audience, strategy, created_at, updated_at, version)
    VALUES (:id, :tenant_id, :project_id, :business_name, :industry, :target_audience, :strategy, :created_at, :updated_at, :version)
    """
    values = {
        "id": hack_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "business_name": business_name,
        "industry": industry,
        "target_audience": target_audience,
        "strategy": strategy,
        "created_at": now,
        "updated_at": now,
        "version": version,
    }
    await database.execute(query=query, values=values)
    return hack_id

# -----------------------------
# Advanced Prompt Builder for Growth Hacker Strategies
# -----------------------------
def build_growth_hack_prompt(request: GrowthHackRequest) -> str:
    prompt = (
        f"You are a world-class growth hacker with an unmatched track record of scaling companies using unconventional, data-driven, "
        "and viral tactics that replace expensive human marketing teams. Your goal is to generate a comprehensive growth strategy for "
        f"the business '{request.business_name}' operating in the '{request.industry or 'general'}' industry.\n\n"
        "Your strategy should include:\n"
        "- Identifying free and low-cost marketing channels (e.g., press releases, influencer partnerships, social media campaigns, SEO, viral loops)\n"
        "- Methods to secure grants, sponsorships, and government funding for marketing\n"
        "- Creative outreach strategies (e.g., email to media, radio, TV, and community partnerships)\n"
        "- Innovative growth hacks like referral programs, content marketing, and viral loops\n"
        "- Detailed action plans, including timelines, resource requirements, and key performance indicators\n"
        "- Specific links and resources where possible (e.g., grant portals, press release distribution services)\n\n"
        f"Target Audience: {request.target_audience or 'a broad audience'}.\n"
        f"Additional Context: {request.additional_context or 'No additional context provided.'}\n"
        f"Language: {request.language}.\n\n"
        "Generate the final, detailed growth hacking strategy that is so impressive it makes one say 'WOW'."
    )
    return prompt

# -----------------------------
# Growth Hacker Strategy Generation Function with Retry Logic
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_growth_hack_strategy(request: GrowthHackRequest) -> str:
    prompt = build_growth_hack_prompt(request)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.75,
            max_tokens=1500
        )
        strategy = response.choices[0].message.content.strip()
        return strategy
    except Exception as e:
        logger.error("Error generating growth hack strategy: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to generate strategy: {str(e)}")

# -----------------------------
# API Endpoints for Growth Hacker Strategies
# -----------------------------
@router.post("/", response_model=GrowthHackResponse)
async def create_growth_hack_plan(
    request: GrowthHackRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder", "GrowthHacker"]))
):
    """
    Generates an AI-driven growth hacking strategy for the given business.
    
    The strategy covers free/low-cost marketing channels, outreach tactics, grant and sponsorship opportunities, viral growth, and more.
    It is stored in SQL with multi-tenant support and versioning.
    Slack notifications are sent on creation.
    """
    strategy = await generate_growth_hack_strategy(request)
    try:
        hack_id = await store_growth_hack(
            request.tenant_id,
            request.project_id,
            request.business_name,
            request.industry,
            request.target_audience,
            strategy,
            version=1
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store growth hack strategy: {str(e)}")
    
    background_tasks.add_task(send_slack_notification, f"New growth hack strategy created for {request.business_name}")
    
    query = """
    SELECT id, tenant_id, project_id, business_name, industry, target_audience, strategy, created_at, updated_at, version
    FROM growth_hacks
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": hack_id})
    if not row:
        raise HTTPException(status_code=500, detail="Failed to retrieve stored growth hack strategy")
    return GrowthHackResponse(**row)

@router.get("/", response_model=List[GrowthHackResponse])
async def list_growth_hack_plans(
    tenant_id: str,
    project_id: str,
    user=Depends(require_role(["CMO", "Founder", "GrowthHacker"]))
):
    query = """
    SELECT id, tenant_id, project_id, business_name, industry, target_audience, strategy, created_at, updated_at, version
    FROM growth_hacks
    WHERE tenant_id = :tenant_id AND project_id = :project_id
    ORDER BY created_at DESC
    """
    rows = await database.fetch_all(query=query, values={"tenant_id": tenant_id, "project_id": project_id})
    return [GrowthHackResponse(**row) for row in rows]

@router.get("/{hack_id}", response_model=GrowthHackResponse)
async def get_growth_hack_plan(hack_id: str, user=Depends(require_role(["CMO", "Founder", "GrowthHacker"]))):
    query = """
    SELECT id, tenant_id, project_id, business_name, industry, target_audience, strategy, created_at, updated_at, version
    FROM growth_hacks
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": hack_id})
    if not row:
        raise HTTPException(status_code=404, detail="Growth hack strategy not found")
    return GrowthHackResponse(**row)

# Additional endpoints for updates, overrides, or A/B testing can be added similarly.

