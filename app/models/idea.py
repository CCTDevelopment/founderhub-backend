from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from uuid import uuid4
from app.core.db import Base

class Idea(Base):
    __tablename__ = "ideas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title = Column(String(255), nullable=False)
    problem = Column(Text, nullable=False)
    audience = Column(Text, nullable=False)
    solution = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)

    vetting_status = Column(String(50), default="pending")
    vetting_response = Column(Text, nullable=True)
    tokens_used = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
