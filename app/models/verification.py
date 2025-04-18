# app/models/verification.py

from sqlalchemy import Column, String, Text, Boolean, DateTime
from app.core.db import Base
from datetime import datetime
import uuid

class EmailVerification(Base):
    __tablename__ = "email_verifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False)
    email = Column(Text, nullable=False)  # renamed from `email` to `to_email`
    token = Column(Text, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
