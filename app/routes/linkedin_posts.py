import os, uuid, logging, requests, httpx, jwt
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, Field
from databases import Database
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
GPU_API_URL = os.getenv("GPU_API_URL")
GPU_API_SECRET = os.getenv("GPU_API_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

database = Database(DATABASE_URL)
config: Dict[str, str] = {}

if not all([DATABASE_URL, GPU_API_URL, GPU_API_SECRET, OPENAI_API_KEY]):
    raise RuntimeError("Missing environment variables")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/linkedin/posts", tags=["LinkedIn Posts"])

# =========================
#  SCHEMAS
# =========================

class LinkedInPostRequest(BaseModel):
    tenant_id: str
    project_id: str
    post_type: str
    campaign_name: Optional[str]
    business_name: str
    tagline: str
    target_audience: Optional[str]
    objectives: Optional[str]
    description: Optional[str] = ""
    style: Optional[str] = "modern"
    language: Optional[str] = "en"
    extra_instructions: Optional[str] = ""

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

# =========================
#  STUBS / AUTH
# =========================

def get_current_user():
    return {"user_id": "demo_user", "tenant_id": "demo_tenant", "role": "CMO"}

def require_role(roles: List[str]):
    def wrapper(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Unauthorized")
        return user
    return wrapper

async def store_linkedin_post(*args, **kwargs): return str(uuid.uuid4())
async def update_linkedin_post_in_db(*args, **kwargs): pass
async def store_override(*args, **kwargs): return str(uuid.uuid4())

# =========================
#  PROMPT + LOGIC
# =========================

def build_prompt(request: LinkedInPostRequest) -> str:
    return (
        "You are a top-tier CMO. Think step-by-step to write a persuasive LinkedIn post.\n\n"
        f"Business: {request.business_name}\n"
        f"Tagline: {request.tagline}\n"
        f"Audience: {request.target_audience or 'professionals'}\n"
        f"Objective: {request.objectives or 'engagement'}\n"
        f"Style: {request.style}\n"
        f"Language: {request.language}\n"
        f"{request.description or ''}\n"
        f"{request.extra_instructions or ''}\n\n"
        "Output only the final LinkedIn post."
    )

def send_slack_notification(msg: str):
    try:
        response = requests.post(config["SLACK_WEBHOOK_URL"], json={"text": msg})
        response.raise_for_status()
        logger.info("Slack notification sent.")
    except Exception as e:
        logger.warning(f"Slack failed: {e}")

async def log_token_usage(user_id: str, tenant_id: str, tokens: int, source: str):
    query = """
        INSERT INTO usage_log (id, user_id, tenant_id, tokens_used, source, endpoint, created_at)
        VALUES (:id, :user_id, :tenant_id, :tokens_used, :source, :endpoint, now())
    """
    await database.execute(query=query, values={
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "tokens_used": tokens,
        "source": source,
        "endpoint": "/linkedin/posts",
    })

# =========================
#  GENERATE POST
# =========================

@retry(stop=stop_after_attempt(2), wait=wait_exponential())
async def generate_post(request: LinkedInPostRequest, user: dict) -> str:
    prompt = build_prompt(request)
    token = jwt.encode({
        "sub": user["user_id"],
        "scope": "founderhub",
        "exp": datetime.utcnow() + timedelta(hours=12),
        "iat": datetime.utcnow()
    }, GPU_API_SECRET, algorithm="HS256")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                GPU_API_URL,
                headers=headers,
                json={"role": "cmo", "prompt": prompt},
                timeout=20
            )
            res.raise_for_status()
            content = res.json().get("response", "").strip()
            token_estimate = len(content.split()) // 0.75  # rough token count
            await log_token_usage(user["user_id"], request.tenant_id, int(token_estimate), "gpu")
            return content

    except Exception as gpu_error:
        logger.warning("GPU failed: %s", gpu_error)

    # Fallback to OpenAI
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "max_tokens": 800
                },
                timeout=30
            )
            res.raise_for_status()
            data = res.json()
            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", len(content.split()) // 0.75)
            await log_token_usage(user["user_id"], request.tenant_id, int(tokens), "openai")
            return content

    except Exception as fallback_error:
        logger.error("OpenAI Fallback failed: %s", fallback_error)
        raise HTTPException(status_code=500, detail="AI generation failed")

# =========================
#  CREATE ENDPOINT
# =========================

@router.post("/", response_model=LinkedInPostResponse)
async def create_linkedin_post(
    request: LinkedInPostRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(["CMO", "Founder"]))
):
    post_copy = await generate_post(request, user)
    li_result = {"linkedin_post_id": f"FAKE-LINKEDIN-{uuid.uuid4()}"}

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

    background_tasks.add_task(
        send_slack_notification,
        f"✅ LinkedIn post created for {request.business_name} by {user['user_id']}"
    )

    return LinkedInPostResponse(
        id=post_id,
        tenant_id=request.tenant_id,
        project_id=request.project_id,
        post_type=request.post_type,
        business_name=request.business_name,
        tagline=request.tagline,
        message=post_copy,
        linkedin_post_id=li_result.get("linkedin_post_id"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        version=1
    )
