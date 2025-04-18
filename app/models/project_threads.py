from sqlalchemy import Column, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
import uuid

from app.core.base import Base

class ProjectThread(Base):
    __tablename__ = "project_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    role = Column(Text, nullable=False)
    assistant_id = Column(Text, nullable=False)
    thread_id = Column(Text, nullable=False)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        # Enforce one thread per project + role
        dict(sqlite_autoincrement=True),
    )
