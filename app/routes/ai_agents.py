from fastapi import APIRouter

router = APIRouter()

@router.get("/ai-agents")
async def get_ai_agents():
    return [{"role": "CEO"}, {"role": "CFO"}]
