from sqlalchemy import Column, String, Text, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import enum
import uuid

from app.core.db import Base

class ProjectStatus(str, enum.Enum):
    idea = "idea"
    in_progress = "in_progress"
    paused = "paused"
    completed = "completed"
    archived = "archived"

class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    type = Column(String)  # Optional: 'saas', 'retail', 'food', etc.
    status = Column(Enum(ProjectStatus), default=ProjectStatus.idea)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
