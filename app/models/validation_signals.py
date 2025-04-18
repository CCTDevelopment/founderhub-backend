from sqlalchemy import Column, String, ForeignKey, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from datetime import datetime
from app.core.db import Base

class ValidationSignal(Base):
    __tablename__ = "validation_signals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=True)
    type = Column(String)  # demo_requested, objection, positive_feedback, etc.
    note = Column(String)
    strength = Column(Integer)  # 1–5 scale
    created_at = Column(DateTime, default=datetime.utcnow)
