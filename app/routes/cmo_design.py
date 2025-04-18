import os
import uuid
import jwt
import httpx
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from databases import Database
from dotenv import load_dotenv
from typing import Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential

# === Load ENV ===
load_dotenv()

GPU_API_URL = os.getenv("GPU_API_URL")
GPU_API_SECRET = os.getenv("GPU_API_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CANVA_API_TOKEN = os.getenv("CANVA_API_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

missing = []
for var in ["GPU_API_URL", "GPU_API_SECRET", "OPENAI_API_KEY", "DATABASE_URL"]:
    if not os.getenv(var):
        missing.append(var)

if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

# === Setup ===
database = Database(DATABASE_URL)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/cmo/design", tags=["CMO Design"])

# === Dummy Auth
def get_current_user():
    return {"user_id": "founderhub", "tenant_id": "demo_tenant", "role": "CMO"}

# === Models
class DesignRequest(BaseModel):
    tenant_id: str
    project_id: str
    design_type: str
    business_name: str
    tagline: str
    brand_guidelines: Optional[str] = None
    target_audience: Optional[str] = None
    objectives: Optional[str] = None
    description: Optional[str] = ""
    style: Optional[str] = "modern"
    extra_instructions: Optional[str] = ""
    language: Optional[str] = "en"

class DesignResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    design_type: str
    business_name: str
    tagline: str
    output: str
    created_at: datetime
    updated_at: datetime
    version: int

# === Prompt Builder
def build_design_prompt(request: DesignRequest) -> str:
    return (
        "You are a high-performance CMO. Think step-by-step and create a design brief.\n\n"
        f"Design Type: {request.design_type}\n"
        f"Business: {request.business_name}\n"
        f"Tagline: {request.tagline}\n"
        f"Audience: {request.target_audience or 'General'}\n"
        f"Objectives: {request.objectives or 'Engagement'}\n"
        f"Style: {request.style}, Language: {request.language}\n"
        f"Guidelines: {request.brand_guidelines or 'Standard modern brand'}\n"
        f"{request.description or ''}\n{request.extra_instructions or ''}\n\n"
        "Return a complete brief."
    )

# === Token Tracker
async def log_token_usage(user_id: str, tenant_id: str, tokens: int, source: str):
    query = """
    INSERT INTO usage_log (id, user_id, tenant_id, tokens_used, source, endpoint, created_at)
    VALUES (:id, :user_id, :tenant_id, :tokens_used, :source, '/cmo/design', now())
    """
    await database.execute(query=query, values={
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "tokens_used": tokens,
        "source": source
    })

# === DB Store Stub
async def store_design_output(*args, **kwargs):
    return str(uuid.uuid4())

# === Generator (GPU + OpenAI)
@retry(stop=stop_after_attempt(2), wait=wait_exponential())
async def generate_design_brief(request: DesignRequest, user_id: str) -> str:
    prompt = build_design_prompt(request)

    # GPU call
    try:
        jwt_token = jwt.encode({
            "sub": user_id,
            "scope": "founderhub",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=12)
        }, GPU_API_SECRET, algorithm="HS256")

        headers = {"Authorization": f"Bearer {jwt_token}"}

        async with httpx.AsyncClient() as client:
            res = await client.post(GPU_API_URL, headers=headers, json={
                "role": "cmo", "prompt": prompt, "stream": False
            }, timeout=30)
            res.raise_for_status()
            content = res.json().get("response", "").strip()
            tokens = len(content.split()) // 0.75
            await log_token_usage(user_id, request.tenant_id, int(tokens), "gpu")
            return content
    except Exception as e:
        logger.warning("GPU fallback: %s", e)

    # OpenAI fallback
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json={
                "model": "gpt-4",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 1500
            }, timeout=40)
            res.raise_for_status()
            data = res.json()
            content = data["choices"][0]["message"]["content"].strip()
            tokens = data.get("usage", {}).get("total_tokens", len(content.split()) // 0.75)
            await log_token_usage(user_id, request.tenant_id, int(tokens), "openai")
            return content
    except Exception as e:
        logger.error("OpenAI fallback failed: %s", e)
        raise HTTPException(status_code=500, detail="All generation failed")

# === Design Endpoint
@router.post("/", response_model=DesignResponse)
async def create_design(
    request: DesignRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user)
):
    brief = await generate_design_brief(request, user["user_id"])
    design_id = await store_design_output(
        request.tenant_id, request.project_id, request.design_type,
        request.business_name, request.tagline, brief
    )
    return DesignResponse(
        id=design_id,
        tenant_id=request.tenant_id,
        project_id=request.project_id,
        design_type=request.design_type,
        business_name=request.business_name,
        tagline=request.tagline,
        output=brief,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        version=1
    )

# === Stream Endpoint
@router.post("/stream")
async def stream_design_response(
    request: DesignRequest,
    req: Request,
    user=Depends(get_current_user)
):
    prompt = build_design_prompt(request)

    jwt_token = jwt.encode({
        "sub": user["user_id"],
        "scope": "founderhub",
        "exp": datetime.utcnow() + timedelta(hours=12),
        "iat": datetime.utcnow()
    }, GPU_API_SECRET, algorithm="HS256")

    headers = {"Authorization": f"Bearer {jwt_token}"}

    async def stream_response():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", GPU_API_URL, headers=headers, json={
                    "role": "cmo", "prompt": prompt, "stream": True
                }) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            yield line.replace("data: ", "") + "\n"
        except Exception as e:
            yield f"[STREAM ERROR]: {str(e)}\n"

    return StreamingResponse(stream_response(), media_type="text/plain")
