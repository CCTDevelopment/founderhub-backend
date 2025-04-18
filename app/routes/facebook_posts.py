import os, uuid, logging, requests, httpx, jwt
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel
from databases import Database
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
GPU_API_URL = os.getenv("GPU_API_URL")
GPU_API_SECRET = os.getenv("GPU_API_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not all([DATABASE_URL, GPU_API_URL, GPU_API_SECRET, OPENAI_API_KEY]):
    raise RuntimeError("Missing one or more required environment variables")

database = Database(DATABASE_URL)
config: Dict[str, str] = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/facebook/posts", tags=["Facebook Posts"])

# ========================
# AUTH + HELPERS
# ========================

def get_current_user():
    return {"user_id": "demo_user", "tenant_id": "demo_tenant", "role": "CMO"}

def require_role(roles: List[str]):
    def wrapper(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Unauthorized")
        return user
    return wrapper

def send_slack_notification(message: str):
    try:
        response = requests.post(config["SLACK_WEBHOOK_URL"], json={"text": message})
        response.raise_for_status()
        logger.info("Slack notification sent.")
    except Exception as e:
        logger.error(f"Slack send failed: {e}")

async def get_config_value(key: str) -> str:
    query = "SELECT config_value FROM system_config WHERE config_key = :key"
    row = await database.fetch_one(query=query, values={"key": key})
    if not row:
        raise RuntimeError(f"Missing config key: {key}")
    return row["config_value"]

async def load_config():
    keys = ["FB_PAGE_TOKEN", "CANVA_API_TOKEN", "SLACK_WEBHOOK_URL"]
    for key in keys:
        config[key] = await get_config_value(key)

# ========================
# SCHEMAS
# ========================

class FacebookPostRequest(BaseModel):
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

class OverrideRequest(BaseModel):
    tenant_id: str
    design_id: str
    override_message: str

# ========================
# STUBBED DB HELPERS
# ========================

async def store_facebook_post(*args, **kwargs) -> str: return str(uuid.uuid4())
async def update_facebook_post_in_db(*args, **kwargs) -> str: return str(uuid.uuid4())
async def store_design_revision(*args, **kwargs): pass
async def store_override(*args, **kwargs): pass
async def fetch_facebook_post_metrics(*args, **kwargs): return {}

# ========================
# TOKEN TRACKING
# ========================

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
        "endpoint": "/facebook/posts"
    })

# ========================
# PROMPT BUILDER
# ========================

def build_prompt(request: FacebookPostRequest) -> str:
    return (
        "You are a high-converting CMO generating a persuasive Facebook post.\n"
        f"Business: {request.business_name}\n"
        f"Tagline: {request.tagline}\n"
        f"Target Audience: {request.target_audience or 'general'}\n"
        f"Objectives: {request.objectives or 'engagement'}\n"
        f"Style: {request.style}, Language: {request.language}\n"
        f"{request.description or ''}\n{request.extra_instructions or ''}\n"
        "Think step-by-step, then write the final Facebook ad copy."
    )

# ========================
# MAIN GENERATOR (GPU + OpenAI fallback)
# ========================

@retry(stop=stop_after_attempt(2), wait=wait_exponential())
async def generate_facebook_post_content(request: FacebookPostRequest, user: dict) -> str:
    prompt = build_prompt(request)
    token = jwt.encode({
        "sub": user["user_id"],
        "scope": "founderhub",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=12)
    }, GPU_API_SECRET, algorithm="HS256")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Attempt GPU first
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
            est_tokens = len(content.split()) // 0.75
            await log_token_usage(user["user_id"], request.tenant_id, int(est_tokens), "gpu")
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
                timeout=40
            )
            res.raise_for_status()
            data = res.json()
            content = data["choices"][0]["message"]["content"].strip()
            tokens = data.get("usage", {}).get("total_tokens", len(content.split()) // 0.75)
            await log_token_usage(user["user_id"], request.tenant_id, int(tokens), "openai")
            return content

    except Exception as openai_error:
        logger.error("OpenAI Fallback failed: %s", openai_error)
        raise HTTPException(status_code=500, detail="AI generation failed")

# ========================
# POST TO FACEBOOK
# ========================

@retry(stop=stop_after_attempt(3), wait=wait_exponential())
def post_to_facebook(message: str) -> dict:
    api_url = "https://graph.facebook.com/me/feed"
    payload = {
        "message": message,
        "access_token": config["FB_PAGE_TOKEN"]
    }
    response = requests.post(api_url, data=payload)
    response.raise_for_status()
    return {"fb_post_id": response.json().get("id")}

# ========================
# MAIN ROUTE
# ========================

@router.post("/", response_model=FacebookPostResponse)
async def create_facebook_post(
    background_tasks: BackgroundTasks,
    request: FacebookPostRequest,
    user=Depends(require_role(["CMO", "Founder"]))
):
    ad_copy = await generate_facebook_post_content(request, user)
    fb_result = post_to_facebook(ad_copy)
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
    background_tasks.add_task(send_slack_notification, f"✅ Facebook post created: {post_id}")
    return FacebookPostResponse(
        id=post_id,
        tenant_id=request.tenant_id,
        project_id=request.project_id,
        post_type=request.post_type,
        message=ad_copy,
        fb_post_id=fb_result.get("fb_post_id"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        version=1
    )
