import os
import uuid
import jwt
import httpx
import logging
import psycopg2
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
router = APIRouter()

# === Config
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL")
OLLAMA_API_SECRET = os.getenv("OLLAMA_API_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not all([OLLAMA_API_URL, OLLAMA_API_SECRET, OPENAI_API_KEY]):
    raise RuntimeError("Missing environment variables")

# === DB Setup
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

def store_research_output(tenant_id, project_id, query, rtype, output):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO research_outputs (
                    id, tenant_id, project_id, research_query, research_type, research_output, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()), tenant_id, project_id, query, rtype, output, datetime.utcnow()
            ))
        conn.commit()
    finally:
        conn.close()

def log_token_usage(user_id, tenant_id, tokens, source):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO usage_log (id, user_id, tenant_id, tokens_used, source, endpoint, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                str(uuid.uuid4()), user_id, tenant_id, tokens, source, "/ai-agents/ai-research-extended", datetime.utcnow()
            ))
        conn.commit()
    finally:
        conn.close()

# === Pydantic
class ResearchRequest(BaseModel):
    tenant_id: str
    project_id: str
    research_query: str
    research_internet: bool = False
    research_type: str = "general"

# === Prompt Builder
def build_research_prompt(query: str, use_web: bool, rtype: str) -> str:
    prompt = (
        "You are a highly advanced AI researcher.\n"
        f"Topic: {query}\n\n"
        "Think step-by-step and provide:\n"
        "- Clear definitions and context\n"
        "- Actionable insights\n"
        "- Examples, code, citations (where needed)\n"
        "- Next steps or implementation advice\n"
    )
    if rtype.lower() == "google research":
        prompt += "\nInclude recent results from Google and summarize findings from trusted sources."
    elif rtype.lower() == "paper review":
        prompt += "\nInclude summaries and citations from academic papers and relevant publications."
    elif rtype.lower() == "ai code development":
        prompt += "\nFocus on AI development and include code examples and architecture notes."

    if use_web:
        prompt += "\nUse current information from the internet if available."

    return prompt

# === AI Generator (GPU + fallback)
@retry(stop=stop_after_attempt(2), wait=wait_exponential())
async def generate_research_output(prompt, tenant_id, user_id) -> str:
    # === Try GPU
    try:
        token = jwt.encode({
            "sub": user_id,
            "scope": "founderhub",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=12)
        }, OLLAMA_API_SECRET, algorithm="HS256")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            res = await client.post(
                OLLAMA_API_URL,
                headers=headers,
                json={"role": "ai researcher", "prompt": prompt},
                timeout=20
            )
            res.raise_for_status()
            content = res.json().get("response", "").strip()
            tokens = int(len(content.split()) / 0.75)
            log_token_usage(user_id, tenant_id, tokens, "gpu")
            return content

    except Exception as gpu_error:
        logging.warning("GPU failed: %s", gpu_error)

    # === Fallback to OpenAI
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
                    "temperature": 0.7,
                    "max_tokens": 1500
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
        raise HTTPException(status_code=500, detail="All AI sources failed")

# === Endpoint
@router.post("/ai-agents/ai-research-extended")
async def generate_research(request: ResearchRequest):
    prompt = build_research_prompt(request.research_query, request.research_internet, request.research_type)
    try:
        output = await generate_research_output(
            prompt,
            tenant_id=request.tenant_id,
            user_id="founderhub"
        )
        store_research_output(request.tenant_id, request.project_id, request.research_query, request.research_type, output)
        return {
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "research_query": request.research_query,
            "research_type": request.research_type,
            "research_internet": request.research_internet,
            "research_output": output
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
