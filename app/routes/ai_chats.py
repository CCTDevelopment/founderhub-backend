from fastapi import APIRouter

router = APIRouter()

@router.get("/ai-chats")
async def get_chats():
    return [{"agent": "BASE CEO", "message": "Let’s move forward with this strategy."}]
