import os
import uuid
from datetime import datetime
from typing import List, Optional

import openai
import psycopg2
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables (ideally done once in your app's entry point)
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Import your authentication dependency
from app.dependencies.auth import get_current_user  # adjust as needed

router = APIRouter()

# --- Pydantic Models ---

class AgentCreate(BaseModel):
    tenant_id: str
    role: str
    description: str
    scope: str
    model: str = Field(default="gpt-4o")
    system_prompt: str

class AgentUpdate(BaseModel):
    role: Optional[str]
    description: Optional[str]
    scope: Optional[str]
    model: Optional[str]
    system_prompt: Optional[str]

class AgentOut(BaseModel):
    id: str
    tenant_id: str
    role: str
    description: str
    scope: str
    model: str
    system_prompt: str
    created_at: datetime
    updated_at: datetime

# --- Database Helpers ---

def get_db_connection():
    """
    Establishes and returns a connection to the Postgres database.
    """
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

def store_agent(agent: AgentCreate, agent_id: str, created_at: datetime, updated_at: datetime):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_agents (id, tenant_id, role, description, scope, model, system_prompt, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    agent_id,
                    agent.tenant_id,
                    agent.role,
                    agent.description,
                    agent.scope,
                    agent.model,
                    agent.system_prompt,
                    created_at,
                    updated_at,
                )
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_agent_in_db(agent_id: str, update_data: dict, updated_at: datetime):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Build dynamic update query based on fields provided
            set_clauses = []
            values = []
            for key, value in update_data.items():
                set_clauses.append(f"{key} = %s")
                values.append(value)
            set_clauses.append("updated_at = %s")
            values.append(updated_at)
            values.append(agent_id)
            query = f"UPDATE ai_agents SET {', '.join(set_clauses)} WHERE id = %s"
            cur.execute(query, tuple(values))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_agent_from_db(agent_id: str) -> Optional[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tenant_id, role, description, scope, model, system_prompt, created_at, updated_at
                FROM ai_agents
                WHERE id = %s
                """,
                (agent_id,)
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "tenant_id": row[1],
                    "role": row[2],
                    "description": row[3],
                    "scope": row[4],
                    "model": row[5],
                    "system_prompt": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                }
    except Exception as e:
        raise e
    finally:
        conn.close()
    return None

def delete_agent_from_db(agent_id: str) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ai_agents WHERE id = %s", (agent_id,))
            affected = cur.rowcount
        conn.commit()
        return affected > 0
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def list_agents_from_db(tenant_id: str) -> List[dict]:
    conn = get_db_connection()
    agents = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tenant_id, role, description, scope, model, system_prompt, created_at, updated_at
                FROM ai_agents
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                """,
                (tenant_id,)
            )
            rows = cur.fetchall()
            for row in rows:
                agents.append({
                    "id": row[0],
                    "tenant_id": row[1],
                    "role": row[2],
                    "description": row[3],
                    "scope": row[4],
                    "model": row[5],
                    "system_prompt": row[6],
                    "created_at": row[7],
                    "updated_at": row[8],
                })
    except Exception as e:
        raise e
    finally:
        conn.close()
    return agents

# --- API Endpoints ---

@router.get("/ai-agents", response_model=List[AgentOut])
async def list_agents(tenant_id: str, user=Depends(get_current_user)):
    """
    Retrieves all AI agents for a given tenant.
    """
    try:
        agents_data = list_agents_from_db(tenant_id)
        return agents_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai-agents", response_model=AgentOut)
async def create_agent(agent: AgentCreate, user=Depends(get_current_user)):
    """
    Creates a new AI agent.
    """
    agent_id = str(uuid.uuid4())
    now = datetime.utcnow()
    try:
        store_agent(agent, agent_id, now, now)
        return {
            "id": agent_id,
            "tenant_id": agent.tenant_id,
            "role": agent.role,
            "description": agent.description,
            "scope": agent.scope,
            "model": agent.model,
            "system_prompt": agent.system_prompt,
            "created_at": now,
            "updated_at": now,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/ai-agents/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str, user=Depends(get_current_user)):
    """
    Retrieves an AI agent by its ID.
    """
    agent_data = get_agent_from_db(agent_id)
    if not agent_data:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_data

@router.put("/ai-agents/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: str, agent: AgentUpdate, user=Depends(get_current_user)):
    """
    Updates an existing AI agent.
    """
    update_data = agent.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No update fields provided")
    now = datetime.utcnow()
    try:
        update_agent_in_db(agent_id, update_data, now)
        updated_agent = get_agent_from_db(agent_id)
        if not updated_agent:
            raise HTTPException(status_code=404, detail="Agent not found after update")
        return updated_agent
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/ai-agents/{agent_id}")
async def delete_agent(agent_id: str, user=Depends(get_current_user)):
    """
    Deletes an AI agent.
    """
    try:
        success = delete_agent_from_db(agent_id)
        if not success:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {"detail": "Agent deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ai-agents/{agent_id}/execute")
async def execute_agent(agent_id: str, user=Depends(get_current_user)):
    """
    Executes the specified AI agent by sending its system prompt to the OpenAI API,
    returning the generated response. This simulates the agent "acting" to drive business growth.
    """
    agent_data = get_agent_from_db(agent_id)
    if not agent_data:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    system_prompt = agent_data["system_prompt"]
    # Here you could combine the system prompt with dynamic context if needed.
    try:
        response = openai.ChatCompletion.create(
            model=agent_data["model"],
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.7,
            max_tokens=800
        )
        result = response.choices[0].message.content.strip()
        return {"agent_id": agent_id, "response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
