from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from uuid import uuid4

Base = declarative_base()

class IdeaSummary(Base):
    __tablename__ = "idea_summary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    idea_id = Column(UUID(as_uuid=True), ForeignKey("ideas.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    summary = Column(Text, nullable=False)
    recommended_team = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
