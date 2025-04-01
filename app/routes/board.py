import os
import uuid
from datetime import datetime
import openai
import psycopg2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables (ideally done once at application startup)
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

router = APIRouter()

class BoardMeetingRequest(BaseModel):
    tenant_id: str
    project_id: str
    meeting_topic: str
    human_direction: str = ""  # Optional additional human insight/direction

def get_db_connection():
    """
    Establish and return a connection to the Postgres database.
    """
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

def get_blueprint(tenant_id: str, project_id: str) -> str:
    """
    Fetches the most recent blueprint from the 'business_blueprints' table for the given tenant and project.
    Returns the blueprint text, or an empty string if none is found.
    """
    conn = get_db_connection()
    blueprint = ""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT blueprint FROM business_blueprints
                WHERE tenant_id = %s AND project_id = %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (tenant_id, project_id)
            )
            row = cur.fetchone()
            if row:
                blueprint = row[0]
    except Exception as e:
        print("Error fetching blueprint:", e)
    finally:
        conn.close()
    return blueprint

def store_board_meeting(tenant_id: str, meeting_topic: str, transcript: str) -> None:
    """
    Stores the board meeting transcript in the 'board_meetings' table.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO board_meetings (id, tenant_id, meeting_topic, transcript, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (str(uuid.uuid4()), tenant_id, meeting_topic, transcript, datetime.utcnow())
            )
        conn.commit()
    finally:
        conn.close()

def build_board_meeting_prompt(meeting_topic: str, blueprint: str, human_direction: str) -> str:
    """
    Constructs a detailed prompt for simulating a board meeting.
    The prompt includes:
      - The meeting topic.
      - Blueprint details from previous planning (if available).
      - Optional human direction for additional guidance.
    """
    prompt = (
        f"You are simulating an executive board meeting for a startup with the meeting topic: '{meeting_topic}'.\n"
        "The board is composed of distinct AI agents with the following roles: CEO, CFO, COO, CTO, and Visionary. "
        "They are tasked with building and scaling the business collaboratively.\n"
    )
    if blueprint:
        prompt += (
            "\nThe latest business blueprint, generated previously, is as follows:\n"
            f"{blueprint}\n"
        )
    if human_direction:
        prompt += (
            "\nAdditionally, here is some human direction to guide the meeting:\n"
            f"{human_direction}\n"
        )
    prompt += (
        "\nSimulate a realistic and dynamic board meeting where these AI executives discuss the blueprint and human direction, "
        "debate differing opinions, and collaboratively outline clear, actionable strategies and next steps to build the business. "
        "Each speaker (CEO, CFO, COO, CTO, and Visionary) must have a distinct voice and provide concrete recommendations. "
        "At the end, include a summary of the action items and responsibilities, clearly labeling each speaker's contribution."
    )
    return prompt

@router.post("/board/meetings")
async def simulate_board_meeting(request: BoardMeetingRequest):
    """
    Simulates a board meeting where a full AI-driven executive team (CEO, CFO, COO, CTO, Visionary)
    discusses business blueprints and human direction to develop actionable plans.
    
    The endpoint:
      1. Fetches the latest blueprint for the given tenant and project.
      2. Builds a prompt that includes the meeting topic, blueprint details, and any human input.
      3. Uses GPT-4 to simulate a dynamic board meeting transcript.
      4. Stores the transcript in SQL and returns it.
    """
    blueprint = get_blueprint(request.tenant_id, request.project_id)
    prompt = build_board_meeting_prompt(request.meeting_topic, blueprint, request.human_direction)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        transcript = response.choices[0].message.content.strip()
        store_board_meeting(request.tenant_id, request.meeting_topic, transcript)
        return {
            "tenant_id": request.tenant_id,
            "meeting_topic": request.meeting_topic,
            "transcript": transcript
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
