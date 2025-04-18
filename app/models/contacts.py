from sqlalchemy import Column, String, ForeignKey, DateTime, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from datetime import datetime
from app.core.db import Base

class Contact(Base):
    __tablename__ = "contacts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    name = Column(String)
    email = Column(String)
    role = Column(String)
    linkedin = Column(String)
    tags = Column(ARRAY(String))
    created_at = Column(DateTime, default=datetime.utcnow)
