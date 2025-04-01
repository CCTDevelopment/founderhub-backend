import os
import json
import uuid
from datetime import datetime
from typing import List, Optional

import psycopg2
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr

# Load environment variables (ideally once at your application startup)
load_dotenv()
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY environment variable is not set!")
fernet = Fernet(ENCRYPTION_KEY.encode())

router = APIRouter()

# Database connection helper
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

# Encryption helpers
def encrypt_value(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()

def decrypt_value(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()

# Pydantic models for Contacts
class ContactCreate(BaseModel):
    tenant_id: str
    user_id: str
    name: str
    role: str
    email: EmailStr
    phone: str
    tags: List[str]
    # Notes are removed from the main contact object.

class ContactUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    tags: Optional[List[str]] = None

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

# Endpoints for Contacts
@router.post("/contacts", response_model=ContactOut)
async def create_contact(contact: ContactCreate):
    conn = get_db_connection()
    contact_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    updated_at = created_at

    encrypted_email = encrypt_value(contact.email)
    encrypted_phone = encrypt_value(contact.phone)
    tags_json = json.dumps(contact.tags)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contacts (id, tenant_id, user_id, name, role, email, phone, tags, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    contact_id,
                    contact.tenant_id,
                    contact.user_id,
                    contact.name,
                    contact.role,
                    encrypted_email,
                    encrypted_phone,
                    tags_json,
                    created_at,
                    updated_at,
                )
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

    return ContactOut(
        id=contact_id,
        tenant_id=contact.tenant_id,
        user_id=contact.user_id,
        name=contact.name,
        role=contact.role,
        email=contact.email,
        phone=contact.phone,
        tags=contact.tags,
        created_at=created_at,
        updated_at=updated_at,
    )

@router.get("/contacts", response_model=List[ContactOut])
async def get_contacts(tenant_id: str = Query(...)):
    conn = get_db_connection()
    contacts = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tenant_id, user_id, name, role, email, phone, tags, created_at, updated_at
                FROM contacts
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                """,
                (tenant_id,)
            )
            rows = cur.fetchall()
            for row in rows:
                contacts.append(
                    ContactOut(
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
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    return contacts

@router.get("/contacts/{contact_id}", response_model=ContactOut)
async def get_contact_by_id(contact_id: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tenant_id, user_id, name, role, email, phone, tags, created_at, updated_at
                FROM contacts
                WHERE id = %s
                """,
                (contact_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Contact not found")
            contact = ContactOut(
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    return contact

@router.put("/contacts/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: str, contact: ContactUpdate):
    conn = get_db_connection()
    updated_at = datetime.utcnow()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM contacts WHERE id = %s", (contact_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Contact not found")

            # Prepare updated values: use new values if provided, otherwise retain existing ones.
            name = contact.name if contact.name is not None else row[3]
            role = contact.role if contact.role is not None else row[4]
            email = encrypt_value(contact.email) if contact.email is not None else row[5]
            phone = encrypt_value(contact.phone) if contact.phone is not None else row[6]
            tags = json.dumps(contact.tags) if contact.tags is not None else row[7]

            cur.execute(
                """
                UPDATE contacts
                SET name = %s, role = %s, email = %s, phone = %s, tags = %s, updated_at = %s
                WHERE id = %s
                """,
                (name, role, email, phone, tags, updated_at, contact_id)
            )
        conn.commit()
    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

    return await get_contact_by_id(contact_id)

@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Contact not found")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    return {"detail": "Contact deleted successfully"}
