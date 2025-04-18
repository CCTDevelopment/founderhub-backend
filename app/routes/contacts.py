import os
import json
import uuid
import logging
from datetime import datetime
from typing import List, Optional

import psycopg2
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr

# === Load .env + encryption setup
load_dotenv()
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY is not set")
fernet = Fernet(ENCRYPTION_KEY.encode())

# === Logger
logger = logging.getLogger("contacts")
logging.basicConfig(level=logging.INFO)

# === FastAPI router
router = APIRouter()

# === DB connection
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

# === Encryption utils
def encrypt_value(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()

def decrypt_value(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()

# === Pydantic Schemas
class ContactCreate(BaseModel):
    tenant_id: str
    user_id: str
    name: str
    role: str
    email: EmailStr
    phone: str
    tags: List[str]

class ContactUpdate(BaseModel):
    name: Optional[str]
    role: Optional[str]
    email: Optional[EmailStr]
    phone: Optional[str]
    tags: Optional[List[str]]

class ContactOut(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    name: str
    role: str
    email: EmailStr
    phone: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime

# === ROUTES

@router.post("/contacts", response_model=ContactOut)
async def create_contact(contact: ContactCreate):
    contact_id = str(uuid.uuid4())
    now = datetime.utcnow()

    encrypted_email = encrypt_value(contact.email)
    encrypted_phone = encrypt_value(contact.phone)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO contacts (id, tenant_id, user_id, name, role, email, phone, tags, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    contact_id, contact.tenant_id, contact.user_id,
                    contact.name, contact.role,
                    encrypted_email, encrypted_phone,
                    json.dumps(contact.tags),
                    now, now
                ))
            conn.commit()
    except Exception as e:
        logger.exception("Failed to create contact")
        raise HTTPException(status_code=500, detail="Database error")

    return ContactOut(
        id=contact_id,
        tenant_id=contact.tenant_id,
        user_id=contact.user_id,
        name=contact.name,
        role=contact.role,
        email=contact.email,
        phone=contact.phone,
        tags=contact.tags,
        created_at=now,
        updated_at=now,
    )

@router.get("/contacts", response_model=List[ContactOut])
async def get_contacts(
    tenant_id: str = Query(...),
    limit: int = Query(50, le=100),
    offset: int = Query(0)
):
    contacts = []

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, tenant_id, user_id, name, role, email, phone, tags, created_at, updated_at
                    FROM contacts
                    WHERE tenant_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (tenant_id, limit, offset))
                rows = cur.fetchall()

                for row in rows:
                    contacts.append(ContactOut(
                        id=row[0],
                        tenant_id=row[1],
                        user_id=row[2],
                        name=row[3],
                        role=row[4],
                        email=decrypt_value(row[5]),
                        phone=decrypt_value(row[6]),
                        tags=json.loads(row[7]),
                        created_at=row[8],
                        updated_at=row[9],
                    ))
    except Exception:
        logger.exception("Error fetching contacts")
        raise HTTPException(status_code=500, detail="Database error")

    return contacts

@router.get("/contacts/count")
async def get_contact_count(tenant_id: str = Query(...)):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM contacts WHERE tenant_id = %s", (tenant_id,))
                count = cur.fetchone()[0]
    except Exception:
        logger.exception("Error counting contacts")
        raise HTTPException(status_code=500, detail="Database error")

    return {"count": count}

@router.get("/contacts/{contact_id}", response_model=ContactOut)
async def get_contact_by_id(contact_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, tenant_id, user_id, name, role, email, phone, tags, created_at, updated_at
                    FROM contacts
                    WHERE id = %s
                """, (contact_id,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Contact not found")

                return ContactOut(
                    id=row[0],
                    tenant_id=row[1],
                    user_id=row[2],
                    name=row[3],
                    role=row[4],
                    email=decrypt_value(row[5]),
                    phone=decrypt_value(row[6]),
                    tags=json.loads(row[7]),
                    created_at=row[8],
                    updated_at=row[9],
                )
    except Exception:
        logger.exception("Error fetching contact by ID")
        raise HTTPException(status_code=500, detail="Database error")

@router.put("/contacts/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: str, contact: ContactUpdate):
    now = datetime.utcnow()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Contact not found")

                updated_name = contact.name or row[3]
                updated_role = contact.role or row[4]
                updated_email = encrypt_value(contact.email) if contact.email else row[5]
                updated_phone = encrypt_value(contact.phone) if contact.phone else row[6]
                updated_tags = json.dumps(contact.tags) if contact.tags else row[7]

                cur.execute("""
                    UPDATE contacts
                    SET name = %s, role = %s, email = %s, phone = %s, tags = %s, updated_at = %s
                    WHERE id = %s
                """, (
                    updated_name, updated_role, updated_email, updated_phone,
                    updated_tags, now, contact_id
                ))
            conn.commit()
    except Exception:
        logger.exception("Failed to update contact")
        raise HTTPException(status_code=500, detail="Database error")

    return await get_contact_by_id(contact_id)

@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Contact not found")
            conn.commit()
    except Exception:
        logger.exception("Failed to delete contact")
        raise HTTPException(status_code=500, detail="Database error")

    return {"detail": "Contact deleted successfully"}
