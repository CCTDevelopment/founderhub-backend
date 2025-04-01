from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from uuid import uuid4
from datetime import datetime

router = APIRouter()

class AIAgent(BaseModel):
    id: str
    role: str
    description: str
    scope: str
    model: str = "gpt-4o"
    system_prompt: str
    created_at: datetime

# In-memory store for demo
agents: List[AIAgent] = []

@router.get("/ai-agents", response_model=List[AIAgent])
async def list_agents():
    return agents

@router.post("/ai-agents", response_model=AIAgent)
async def create_agent(agent: AIAgent):
    agent.id = str(uuid4())
    agent.created_at = datetime.now()
    agents.append(agent)
    return agent
