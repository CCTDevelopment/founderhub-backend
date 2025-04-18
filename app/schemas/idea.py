from pydantic import BaseModel

class IdeaCreate(BaseModel):
    title: str
    problem: str
    audience: str
    solution: str
    notes: str
