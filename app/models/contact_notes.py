from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from datetime import datetime
from app.core.db import Base

class ContactNote(Base):
    __tablename__ = "contact_notes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    message = Column(String)
    channel = Column(String)  # email, linkedin, call, etc.
    source = Column(String)   # manual, webhook, etc.
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
