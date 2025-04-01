from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4
from datetime import datetime

router = APIRouter()

# In-memory store for demo
personality_db = {}

class PersonalityProfile(BaseModel):
    user_id: str
    tone: Optional[str] = None  # Friendly, Direct, Formal, etc
    format: Optional[str] = None  # Bullets, Paragraphs
    length: Optional[str] = None  # Brief, Detailed
    analogies: Optional[str] = None  # Yes, No
    asks_questions: Optional[bool] = False
    preferred_examples: Optional[str] = None  # Technical, Story-based, etc
    goals: Optional[str] = None
    style_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@router.get("/personality/{user_id}", response_model=PersonalityProfile)
async def get_personality(user_id: str):
    if user_id not in personality_db:
        raise HTTPException(status_code=404, detail="Personality profile not found")
    return personality_db[user_id]

@router.post("/personality", response_model=PersonalityProfile)
async def set_personality(profile: PersonalityProfile):
    now = datetime.utcnow()
    profile.created_at = now
    profile.updated_at = now
    personality_db[profile.user_id] = profile
    return profile

@router.get("/personality/check/{user_id}")
async def check_personality(user_id: str):
    if user_id in personality_db:
        return {"requires_personality": False}
    return {"requires_personality": True}
