import os
import uuid
from datetime import datetime
from typing import Optional, List

import openai
import requests
import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from databases import Database
from tenacity import retry, stop_after_attempt, wait_exponential

# Load environment variables (should be done at application startup)
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CANVA_API_TOKEN = os.getenv("CANVA_API_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")
if not CANVA_API_TOKEN:
    raise RuntimeError("CANVA_API_TOKEN not set")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")
if not SLACK_WEBHOOK_URL:
    raise RuntimeError("SLACK_WEBHOOK_URL not set")

openai.api_key = OPENAI_API_KEY
database = Database(DATABASE_URL)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cmo/design", tags=["CMO Design"])

# -----------------------------
# Authentication & RBAC
# -----------------------------
def get_current_user():
    # Dummy authentication; replace with your real auth
    return {"user_id": "dummy_user", "tenant_id": "dummy_tenant", "role": "CMO"}

def require_role(required_roles: List[str]):
    def role_checker(user=Depends(get_current_user)):
        if user.get("role") not in required_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return role_checker

# -----------------------------
# Notification Function (Slack Integration)
# -----------------------------
def send_slack_notification(message: str):
    payload = {"text": message}
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        logger.info("Slack notification sent: %s", message)
    except Exception as e:
        logger.error("Failed to send Slack notification: %s", e)

# -----------------------------
# Pydantic Models
# -----------------------------
class DesignRequest(BaseModel):
    tenant_id: str
    project_id: str
    design_type: str = Field(..., description="e.g., 'logo', 'business card', 'billboard', 'road sign', 'flyer', 'brochure'")
    business_name: str
    tagline: str
    brand_guidelines: Optional[str] = Field(None, description="Brand guidelines (fonts, colors, imagery)")
    target_audience: Optional[str] = Field(None, description="Target audience for the design")
    objectives: Optional[str] = Field(None, description="Key messages and goals for the design")
    description: Optional[str] = Field("", description="Additional design details")
    style: Optional[str] = Field("modern", description="Design style (modern, vintage, minimalist, etc.)")
    extra_instructions: Optional[str] = Field("", description="Any extra instructions")
    language: Optional[str] = Field("en", description="Language code (e.g., 'en', 'es', 'fr')")

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

class FeedbackRequest(BaseModel):
    tenant_id: str
    design_id: str
    feedback: str

class OverrideRequest(BaseModel):
    tenant_id: str
    design_id: str
    override_message: str

# -----------------------------
# Database Helper Functions (Async)
# -----------------------------
async def store_design_output(
    tenant_id: str,
    project_id: str,
    design_type: str,
    business_name: str,
    tagline: str,
    output: str,
    version: int = 1
) -> str:
    design_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO design_outputs (id, tenant_id, project_id, design_type, business_name, tagline, output, created_at, updated_at, version)
    VALUES (:id, :tenant_id, :project_id, :design_type, :business_name, :tagline, :output, :created_at, :updated_at, :version)
    """
    values = {
        "id": design_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "design_type": design_type,
        "business_name": business_name,
        "tagline": tagline,
        "output": output,
        "created_at": now,
        "updated_at": now,
        "version": version,
    }
    await database.execute(query=query, values=values)
    return design_id

async def update_design_output(design_id: str, output: str, version: int) -> None:
    now = datetime.utcnow()
    query = """
    UPDATE design_outputs
    SET output = :output, updated_at = :updated_at, version = :version
    WHERE id = :id
    """
    values = {"id": design_id, "output": output, "updated_at": now, "version": version}
    await database.execute(query=query, values=values)

async def store_design_revision(design_id: str, revision_number: int, notes: str) -> str:
    revision_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO design_revisions (id, design_id, revision_number, notes, created_at)
    VALUES (:id, :design_id, :revision_number, :notes, :created_at)
    """
    values = {
        "id": revision_id,
        "design_id": design_id,
        "revision_number": revision_number,
        "notes": notes,
        "created_at": now,
    }
    await database.execute(query=query, values=values)
    return revision_id

async def store_override(tenant_id: str, design_id: str, override_message: str) -> str:
    override_id = str(uuid.uuid4())
    now = datetime.utcnow()
    query = """
    INSERT INTO overrides (id, tenant_id, design_id, override_message, created_at)
    VALUES (:id, :tenant_id, :design_id, :override_message, :created_at)
    """
    values = {
        "id": override_id,
        "tenant_id": tenant_id,
        "design_id": design_id,
        "override_message": override_message,
        "created_at": now,
    }
    await database.execute(query=query, values=values)
    return override_id

# -----------------------------
# Advanced Prompt Builders (with Localization)
# -----------------------------
def build_logo_prompt(request: DesignRequest) -> str:
    prompt = (
        f"Design an iconic, scalable, and visually striking logo for '{request.business_name}' with the tagline '{request.tagline}'. "
        f"Follow these brand guidelines: {request.brand_guidelines or 'Default modern branding'}. "
        f"Target Audience: {request.target_audience or 'a broad audience'}. "
        f"Objectives: {request.objectives or 'innovation and market leadership'}. "
        f"Style: {request.style}. Use language '{request.language}'. "
        "Output only the final image URL."
    )
    if request.description:
        prompt += f" Additional details: {request.description}."
    if request.extra_instructions:
        prompt += f" Extra instructions: {request.extra_instructions}."
    return prompt

def build_design_brief_prompt(request: DesignRequest) -> str:
    prompt = (
        f"You are an award-winning CMO determined to replace human designers with AI-driven creativity. "
        f"Generate a comprehensive design brief for a {request.design_type} for '{request.business_name}' with the tagline '{request.tagline}'.\n\n"
        "Your brief must include:\n"
        "- Detailed layout and structure (dimensions, spacing, hierarchy)\n"
        "- A complete color scheme with specific color recommendations\n"
        "- Font and typography recommendations that align with the brand identity\n"
        "- Wording and messaging for effective communication and a clear call-to-action\n"
        "- Imagery, icons, and graphic element recommendations\n"
        "- Adaptation guidelines for different marketing collateral (business cards, billboards, road signs, flyers, brochures)\n\n"
        f"Brand Guidelines: {request.brand_guidelines or 'Standard modern branding principles.'}\n"
        f"Target Audience: {request.target_audience or 'Not specified'}\n"
        f"Objectives: {request.objectives or 'Not specified'}\n"
        f"Style: {request.style}\n"
        f"Language: {request.language}\n"
    )
    if request.description:
        prompt += f"Additional details: {request.description}\n"
    if request.extra_instructions:
        prompt += f"Extra instructions: {request.extra_instructions}\n"
    prompt += "\nProvide an innovative, actionable, and fully detailed design brief that surpasses standard human creativity."
    return prompt

# -----------------------------
# Design Generation Functions with Retry Logic
# -----------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_logo_design(request: DesignRequest) -> str:
    prompt = build_logo_prompt(request)
    try:
        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="512x512"
        )
        image_url = response["data"][0]["url"]
        return image_url
    except Exception as e:
        logger.error("DALL-E generation error: %s", e)
        raise

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_design_brief(request: DesignRequest) -> str:
    prompt = build_design_brief_prompt(request)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=1500
        )
        design_brief = response.choices[0].message.content.strip()
        return design_brief
    except Exception as e:
        logger.error("ChatGPT generation error: %s", e)
        raise

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_canva_design(design_brief: str) -> str:
    canva_url = "https://api.canva.com/v1/designs"  # Hypothetical endpoint
    headers = {
        "Authorization": f"Bearer {os.getenv('CANVA_API_TOKEN')}",
        "Content-Type": "application/json"
    }
    payload = {
        "design_brief": design_brief,
        "template": "advanced_marketing",
    }
    try:
        response = requests.post(canva_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        design_url = data.get("design_url")
        if not design_url:
            raise Exception("No design URL returned from Canva")
        return design_url
    except Exception as e:
        logger.error("Canva API error: %s", e)
        # Fallback: return the design brief if Canva fails
        return design_brief

# -----------------------------
# API Endpoints
# -----------------------------
@router.post("/", response_model=DesignResponse)
async def create_design(request: DesignRequest, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """
    Fully automates the creation of marketing designs for FounderHub.AI.
    
    - For 'logo', uses DALL-E to generate an image URL.
    - For other types, uses GPT-4 to generate a detailed design brief then calls Canva's API to produce a final design.
      If Canva fails, returns the design brief.
    
    The final output is stored in SQL with tenant and project IDs and versioning.
    Real-time notifications are sent via Slack.
    """
    if request.design_type.lower() == "logo":
        output = await generate_logo_design(request)
    else:
        design_brief = await generate_design_brief(request)
        output = await generate_canva_design(design_brief)
    
    try:
        design_id = await store_design_output(
            request.tenant_id,
            request.project_id,
            request.design_type,
            request.business_name,
            request.tagline,
            output,
            version=1
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store design output: {str(e)}")
    
    background_tasks.add_task(send_slack_notification, f"New design generated for {request.business_name}")
    
    query = """
    SELECT id, tenant_id, project_id, design_type, business_name, tagline, output, created_at, updated_at, version
    FROM design_outputs
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": design_id})
    if not row:
        raise HTTPException(status_code=500, detail="Failed to retrieve stored design output")
    return DesignResponse(**row)

@router.put("/{design_id}", response_model=DesignResponse)
async def update_design(design_id: str, request: DesignRequest, revision_notes: str = "", background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """
    Updates an existing design, creating a new revision.
    
    - Generates a new design output based on updated parameters.
    - Increments the version.
    - Stores a revision note.
    - Returns the updated design output.
    - Sends a Slack notification.
    """
    if request.design_type.lower() == "logo":
        new_output = await generate_logo_design(request)
    else:
        design_brief = await generate_design_brief(request)
        new_output = await generate_canva_design(design_brief)
    
    query = "SELECT version FROM design_outputs WHERE id = :id"
    current_design = await database.fetch_one(query=query, values={"id": design_id})
    if not current_design:
        raise HTTPException(status_code=404, detail="Design not found")
    new_version = current_design["version"] + 1
    
    await update_design_output(design_id, new_output, new_version)
    await store_design_revision(design_id, new_version, revision_notes)
    
    background_tasks.add_task(send_slack_notification, f"Design {design_id} updated to version {new_version}")
    
    query = """
    SELECT id, tenant_id, project_id, design_type, business_name, tagline, output, created_at, updated_at, version
    FROM design_outputs
    WHERE id = :id
    """
    updated_design = await database.fetch_one(query=query, values={"id": design_id})
    if not updated_design:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated design")
    return DesignResponse(**updated_design)

@router.get("/", response_model=List[DesignResponse])
async def list_designs(tenant_id: str, project_id: str, user=Depends(get_current_user)):
    query = """
    SELECT id, tenant_id, project_id, design_type, business_name, tagline, output, created_at, updated_at, version
    FROM design_outputs
    WHERE tenant_id = :tenant_id AND project_id = :project_id
    ORDER BY created_at DESC
    """
    rows = await database.fetch_all(query=query, values={"tenant_id": tenant_id, "project_id": project_id})
    return [DesignResponse(**row) for row in rows]

@router.get("/{design_id}", response_model=DesignResponse)
async def get_design(design_id: str, user=Depends(get_current_user)):
    query = """
    SELECT id, tenant_id, project_id, design_type, business_name, tagline, output, created_at, updated_at, version
    FROM design_outputs
    WHERE id = :id
    """
    row = await database.fetch_one(query=query, values={"id": design_id})
    if not row:
        raise HTTPException(status_code=404, detail="Design not found")
    return DesignResponse(**row)

@router.delete("/{design_id}")
async def delete_design(design_id: str, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    query = "DELETE FROM design_outputs WHERE id = :id"
    result = await database.execute(query=query, values={"id": design_id})
    if not result:
        raise HTTPException(status_code=404, detail="Design not found or already deleted")
    background_tasks.add_task(send_slack_notification, f"Design {design_id} deleted")
    return {"detail": "Design deleted successfully"}

@router.post("/{design_id}/feedback", response_model=DesignResponse)
async def submit_design_feedback(design_id: str, feedback: FeedbackRequest, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """
    Accepts feedback on an existing design and triggers a new revision.
    The feedback is merged with the existing design instructions to generate an updated output.
    """
    original_query = """
    SELECT tenant_id, project_id, design_type, business_name, tagline, brand_guidelines, target_audience, objectives, description, style, extra_instructions, language
    FROM design_outputs
    WHERE id = :id
    """
    original = await database.fetch_one(query=original_query, values={"id": design_id})
    if not original:
        raise HTTPException(status_code=404, detail="Design not found")
    
    design_req = DesignRequest(
        tenant_id=original["tenant_id"],
        project_id=original["project_id"],
        design_type=original["design_type"],
        business_name=original["business_name"],
        tagline=original["tagline"],
        brand_guidelines=original.get("brand_guidelines", ""),
        target_audience=original.get("target_audience", ""),
        objectives=original.get("objectives", ""),
        description=(original.get("description", "") + " " + feedback.feedback).strip(),
        style=original.get("style", "modern"),
        extra_instructions=original.get("extra_instructions", ""),
        language=original.get("language", "en")
    )
    
    if design_req.design_type.lower() == "logo":
        new_output = await generate_logo_design(design_req)
    else:
        design_brief = await generate_design_brief(design_req)
        new_output = await generate_canva_design(design_brief)
    
    query = "SELECT version FROM design_outputs WHERE id = :id"
    current_design = await database.fetch_one(query=query, values={"id": design_id})
    if not current_design:
        raise HTTPException(status_code=404, detail="Design not found")
    new_version = current_design["version"] + 1
    
    await update_design_output(design_id, new_output, new_version)
    await store_design_revision(design_id, new_version, feedback.feedback)
    
    background_tasks.add_task(send_slack_notification, f"Design {design_id} updated via feedback to version {new_version}")
    
    query = """
    SELECT id, tenant_id, project_id, design_type, business_name, tagline, output, created_at, updated_at, version
    FROM design_outputs
    WHERE id = :id
    """
    updated_design = await database.fetch_one(query=query, values={"id": design_id})
    if not updated_design:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated design")
    return DesignResponse(**updated_design)

@router.post("/{design_id}/override", response_model=DesignResponse)
async def override_design(decision: OverrideRequest, background_tasks: BackgroundTasks, user=Depends(get_current_user)):
    """
    Allows the founder (tenant) to override an AI-generated design decision.
    The override is stored, and a notification is sent.
    """
    try:
        await store_override(decision.tenant_id, decision.design_id, decision.override_message)
        background_tasks.add_task(send_slack_notification, f"Override applied to design {decision.design_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    query = """
    SELECT id, tenant_id, project_id, design_type, business_name, tagline, output, created_at, updated_at, version
    FROM design_outputs
    WHERE id = :id
    """
    updated_design = await database.fetch_one(query=query, values={"id": decision.design_id})
    if not updated_design:
        raise HTTPException(status_code=404, detail="Design not found after override")
    return DesignResponse(**updated_design)

@router.post("/{design_id}/abtest")
async def run_ab_test(design_id: str, variant: str = Query(...), user=Depends(get_current_user)):
    """
    Triggers an A/B test for a design variant.
    In a full implementation, this would deploy variant designs, track performance, and store results.
    """
    # For demonstration, we simulate an A/B test trigger.
    background_tasks = BackgroundTasks()
    background_tasks.add_task(send_slack_notification, f"A/B test triggered for design {design_id} with variant '{variant}'")
    return {"detail": f"A/B test for design {design_id} with variant '{variant}' triggered."}
