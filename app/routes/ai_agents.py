import os
import uuid
import logging
import jwt
import httpx
import psycopg2
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

# Load environment variables
load_dotenv()

# === ENV CONFIG ===
router = APIRouter()
GPU_API_URL = os.getenv("GPU_API_URL")
GPU_API_SECRET = os.getenv("GPU_API_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not all([GPU_API_URL, GPU_API_SECRET, OPENAI_API_KEY]):
    raise RuntimeError("Missing required environment variables")

# === DB ===
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

def store_blueprint(tenant_id: str, project_id: str, role: str, blueprint: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO business_blueprints (id, tenant_id, project_id, role, blueprint, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()), tenant_id, project_id, role, blueprint, datetime.utcnow()
            ))
        conn.commit()
    finally:
        conn.close()

def log_token_usage(user_id: str, tenant_id: str, tokens: int, source: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO usage_log (id, user_id, tenant_id, tokens_used, source, endpoint, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()), user_id, tenant_id, tokens, source,
                "/ai-agents/build-business", datetime.utcnow()
            ))
        conn.commit()
    finally:
        conn.close()

# === MODELS ===
class BlueprintRequest(BaseModel):
    tenant_id: str
    project_id: str
    role: str  # e.g. "ceo", "cfo", "visionary", etc.

# === PROMPT BUILDER ===
def build_prompt(role: str) -> str:
    role = role.lower()
    if role == "ceo":
        return (
            "You are a CEO. Think step-by-step to design a startup blueprint:\n"
            "1. Vision\n2. Business Model\n3. Automation\n4. Milestones\n5. Org Structure"
        )
    elif role == "cfo":
        return (
            "You are a CFO. Design a financial plan:\n"
            "1. Forecasting\n2. Budgets\n3. Burn Rate\n4. Revenue Model\n5. Risk"
        )
    elif role == "coo":
        return (
            "You are a COO. Map out operations:\n"
            "1. Infrastructure\n2. Processes\n3. KPIs\n4. Hiring\n5. Tools"
        )
    elif role == "cto":
        return (
            "You are a CTO. Plan the technology stack:\n"
            "1. Architecture\n2. DevOps\n3. ML Infrastructure\n4. AI Automation\n5. Security"
        )
    elif role in ["visionary", "visionair"]:
        return (
            "You are a visionary founder. Envision the future:\n"
            "1. Market Trends\n2. Disruption Areas\n3. Culture\n4. Thought Leadership\n5. Roadmap"
        )
    elif role == "ai researcher":
        return (
            "You are an AI researcher. Develop an AI implementation blueprint:\n"
            "1. Use Cases\n2. Model Types\n3. Dataset Strategy\n4. Ethics\n5. Tooling"
        )
    else:
        return f"You are a strategic executive in the role of {role}. Build a full plan step-by-step."

# === MAIN AI GENERATOR ===
@retry(stop=stop_after_attempt(2), wait=wait_exponential())
async def generate_blueprint(prompt: str, role: str, tenant_id: str, user_id: str) -> str:
    # === Try GPU
    try:
        token = jwt.encode({
            "sub": user_id,
            "scope": "founderhub",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=12)
        }, GPU_API_SECRET, algorithm="HS256")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        model = "llama3:8b" if role != "codegamma" else "codegemma:latest"

        async with httpx.AsyncClient() as client:
            res = await client.post(
                GPU_API_URL,
                headers=headers,
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=20
            )
            res.raise_for_status()
            content = res.json().get("response", "").strip()
            tokens = int(len(content.split()) / 0.75)
            log_token_usage(user_id, tenant_id, tokens, "gpu")
            return content

    except Exception as gpu_error:
        logging.warning("GPU fallback triggered: %s", gpu_error)

    # === OpenAI fallback
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
                    "max_tokens": 1000
                },
                timeout=40
            )
            res.raise_for_status()
            data = res.json()
            content = data["choices"][0]["message"]["content"].strip()
            tokens = data.get("usage", {}).get("total_tokens", int(len(content.split()) / 0.75))
            log_token_usage(user_id, tenant_id, tokens, "openai")
            return content

    except Exception as openai_error:
        logging.error("OpenAI Fallback failed: %s", openai_error)
        raise HTTPException(status_code=500, detail="AI generation failed")

# === API Endpoint ===
@router.post("/ai-agents/build-business")
async def build_business_blueprint(request: BlueprintRequest):
    prompt = build_prompt(request.role)
    try:
        blueprint = await generate_blueprint(
            prompt=prompt,
            role=request.role,
            tenant_id=request.tenant_id,
            user_id="founderhub"
        )
        store_blueprint(request.tenant_id, request.project_id, request.role, blueprint)
        return {
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "role": request.role,
            "blueprint": blueprint
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
