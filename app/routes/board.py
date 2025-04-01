from fastapi import APIRouter

router = APIRouter()

@router.get("/board")
async def get_board_meetings():
    return [{"id": 1, "status": "scheduled"}]
