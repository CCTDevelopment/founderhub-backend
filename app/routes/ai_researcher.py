import os
import uuid
from datetime import datetime
import openai
import psycopg2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables (ideally done once at your application startup)
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

router = APIRouter()

class ResearchRequest(BaseModel):
    tenant_id: str
    project_id: str
    research_query: str
    research_internet: bool = False  # If True, incorporate recent online research
    research_type: str = "general"   # e.g., "general", "google research", "paper review", "AI code development"

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

def store_research_output(tenant_id: str, project_id: str, research_query: str, research_type: str, research_output: str) -> None:
    """
    Stores the generated research output into the 'research_outputs' table.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research_outputs (id, tenant_id, project_id, research_query, research_type, research_output, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (str(uuid.uuid4()), tenant_id, project_id, research_query, research_type, research_output, datetime.utcnow())
            )
        conn.commit()
    finally:
        conn.close()

def build_research_prompt(query: str, research_internet: bool, research_type: str) -> str:
    """
    Constructs a research prompt tailored to the specified research type.
    If research_internet is True, instruct the AI to incorporate recent online research.
    """
    base_prompt = (
        f"You are an expert researcher with deep knowledge in technology, AI, and software development. "
        f"Conduct a comprehensive research analysis on the following topic:\n\n"
        f"Topic: {query}\n\n"
        "Your analysis should include:\n"
        "- A clear explanation of key concepts and background.\n"
        "- Actionable insights and recommendations.\n"
        "- Relevant examples and, where applicable, code snippets or citations.\n"
        "- Potential next steps for further research.\n"
    )
    
    # Append type-specific instructions
    if research_type.lower() == "google research":
        type_instructions = (
            "\nIn addition to your internal knowledge, incorporate recent results from Google searches and summarize findings from trusted online sources. "
            "Reference current trends and data where applicable."
        )
    elif research_type.lower() == "paper review":
        type_instructions = (
            "\nIn addition to your internal knowledge, review relevant academic papers and summarize key findings with citations where possible. "
            "Include insights from recent research publications."
        )
    elif research_type.lower() == "ai code development":
        type_instructions = (
            "\nFocus on generating practical AI code development insights. Include detailed code examples, best practices, and potential libraries or frameworks to use."
        )
    else:
        type_instructions = ""
    
    internet_instructions = (
        "\nAlso incorporate recent information from the internet, including trusted online sources, if available."
        if research_internet else ""
    )
    
    return base_prompt + type_instructions + internet_instructions

@router.post("/ai-agents/ai-research-extended")
async def generate_research_output(request: ResearchRequest):
    """
    Generates a comprehensive research analysis based on the provided research query, research type, and internet research flag.
    
    The analysis includes actionable insights, relevant examples (including AI code snippets or academic citations if applicable),
    and suggestions for further steps. The generated output is stored in SQL along with tenant and project details.
    """
    prompt = build_research_prompt(request.research_query, request.research_internet, request.research_type)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        research_output = response.choices[0].message.content.strip()
        # Store the research output in the database with tenant and project information
        store_research_output(request.tenant_id, request.project_id, request.research_query, request.research_type, research_output)
        return {
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "research_query": request.research_query,
            "research_type": request.research_type,
            "research_internet": request.research_internet,
            "research_output": research_output
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
