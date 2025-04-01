# app/routes/contacts.py

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from typing import List

router = APIRouter()

class Contact(BaseModel):
    name: str
    role: str
    email: EmailStr
    phone: str
    tags: List[str]

@router.get("/contacts", response_model=List[Contact])
async def get_contacts():
    return [
        {
            "name": "Emily Carter",
            "role": "Advisor",
            "email": "emily@email.com",
            "phone": "+1 555-123-4567",
            "tags": ["marketing", "strategy"]
        },
        {
            "name": "John Smith",
            "role": "Potential User",
            "email": "john@email.com",
            "phone": "+1 555-987-6543",
            "tags": ["user", "feedback"]
        },
    ]
