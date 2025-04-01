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

class BlueprintRequest(BaseModel):
    tenant_id: str
    project_id: str
    role: str  # e.g., "CEO", "CFO", "COO", "CTO", "Visionary", etc.

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

def store_blueprint(tenant_id: str, project_id: str, role: str, blueprint: str) -> None:
    """
    Stores the generated blueprint in the 'business_blueprints' table with tenant and project identifiers.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO business_blueprints (id, tenant_id, project_id, role, blueprint, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (str(uuid.uuid4()), tenant_id, project_id, role, blueprint, datetime.utcnow())
            )
        conn.commit()
    finally:
        conn.close()

def build_prompt(role: str) -> str:
    """
    Constructs a detailed prompt for generating a business-building blueprint based on the executive role.
    """
    role_lower = role.lower()
    if role_lower in ["ceo", "co-founder", "ceo/co-founder"]:
        prompt = (
            "You are an experienced CEO and Co-Founder with a proven track record of building successful startups from scratch. "
            "Provide a detailed, step-by-step blueprint for building a new business that includes the following components:\n\n"
            "1. **Vision and Mission:** Define a clear vision and mission statement for the company.\n\n"
            "2. **Business Plan:** Outline a complete business plan, including market analysis, product strategy, target customer segments, revenue models, and competitive analysis.\n\n"
            "3. **Key AI Bots and Automation Systems:** Identify and describe essential AI bots and automation systems for functions such as marketing, customer service, data analytics, operations, and finance.\n\n"
            "4. **Actionable Tasks and Milestones:** Provide a comprehensive list of actionable steps and milestones, including timelines, priorities, and resource requirements.\n\n"
            "5. **Company Infrastructure and Team Setup:** Explain how to set up the company's infrastructure, including the technology stack, organizational structure, team roles, and operational workflows.\n\n"
            "Your response should be structured, clear, and contain specific, actionable items that a founder can follow to build the business from the ground up."
        )
    elif role_lower == "cfo":
        prompt = (
            "You are an experienced CFO with deep expertise in financial management and strategy. "
            "Provide a detailed, step-by-step blueprint for building a robust financial infrastructure for a startup. "
            "Include the following components:\n\n"
            "1. **Financial Strategy and Planning:** Outline strategies for budgeting, fundraising, and financial forecasting.\n\n"
            "2. **Financial Systems and Tools:** Recommend key systems and AI-driven tools for automated bookkeeping, expense management, and financial reporting.\n\n"
            "3. **Risk Management:** Describe methods to identify, assess, and mitigate financial risks.\n\n"
            "4. **Investor Relations:** Provide guidance on managing investor communications and reporting.\n\n"
            "5. **Operational Efficiency:** Detail steps to optimize cash flow and reduce inefficiencies.\n\n"
            "Your response should include clear, actionable items that a CFO can implement to build a strong financial foundation."
        )
    elif role_lower == "coo":
        prompt = (
            "You are an experienced COO with extensive operational expertise in scaling startups. "
            "Provide a detailed, step-by-step blueprint for establishing efficient and scalable operations. "
            "Include the following components:\n\n"
            "1. **Operational Strategy:** Outline strategies for planning, process optimization, and quality control.\n\n"
            "2. **Infrastructure Setup:** Detail how to build and optimize company infrastructure including logistics, supply chain management, and workflow automation.\n\n"
            "3. **Team and Culture:** Explain how to build and manage high-performing teams and foster a productive company culture.\n\n"
            "4. **Technology and Automation:** Identify key operational tools and AI-driven systems to automate repetitive tasks.\n\n"
            "5. **Performance Metrics:** Provide guidance on establishing key performance indicators (KPIs) and continuous improvement systems.\n\n"
            "Your response should be structured and include actionable steps for a COO to implement operational excellence."
        )
    elif role_lower == "cto":
        prompt = (
            "You are an experienced CTO with deep technical expertise in building scalable technology platforms. "
            "Provide a detailed, step-by-step blueprint for establishing the technical foundation of a startup. "
            "Include the following components:\n\n"
            "1. **Technology Vision and Strategy:** Define a clear technology vision and roadmap that aligns with the company's goals.\n\n"
            "2. **Product Development:** Outline the product development lifecycle including ideation, prototyping, development, and launch.\n\n"
            "3. **Tech Stack and Infrastructure:** Recommend an optimal technology stack and infrastructure setup, including cloud services, databases, and security measures.\n\n"
            "4. **Team Building and Culture:** Explain how to build a high-performing engineering team and foster a culture of innovation.\n\n"
            "5. **Automation and AI:** Identify key AI and automation tools to streamline development processes and improve product quality.\n\n"
            "Your response should include actionable items for a CTO to build a robust technical foundation."
        )
    elif role_lower in ["visionary", "visionair"]:
        prompt = (
            "You are a visionary leader with the ability to see market trends and emerging opportunities. "
            "Provide a detailed blueprint for defining and executing a transformative vision for a startup. "
            "Include the following components:\n\n"
            "1. **Vision and Mission:** Define a compelling vision and mission that inspires innovation and long-term growth.\n\n"
            "2. **Market Trends and Opportunities:** Explain how to identify emerging trends and untapped market opportunities.\n\n"
            "3. **Strategic Innovation:** Outline strategies for fostering innovation, including R&D, disruptive technologies, and strategic partnerships.\n\n"
            "4. **Leadership and Culture:** Provide guidance on building a culture that embraces change and continuous learning.\n\n"
            "5. **Execution Roadmap:** Offer a step-by-step plan for translating visionary ideas into actionable strategies and milestones.\n\n"
            "Your response should be forward-thinking and provide concrete steps for a visionary leader to drive transformative growth."
        )
    else:
        prompt = (
            f"You are an experienced executive in the role of {role}. "
            "Provide a detailed, step-by-step blueprint covering the key strategic areas relevant to your role, which a startup can follow to build and scale its business. "
            "Include actionable items, clear milestones, and recommendations for leveraging AI and automation where appropriate."
        )
    return prompt

@router.post("/ai-agents/build-business")
async def build_business_blueprint(request: BlueprintRequest):
    """
    Generates a detailed blueprint for building a business from an executive perspective,
    based on the provided tenant, project, and role information.
    
    The blueprint is generated using GPT-4 and then stored in SQL for record-keeping.
    """
    prompt = build_prompt(request.role)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500
        )
        blueprint = response.choices[0].message.content.strip()
        # Store the blueprint with tenant and project information
        store_blueprint(request.tenant_id, request.project_id, request.role, blueprint)
        return {
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "role": request.role,
            "blueprint": blueprint
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
