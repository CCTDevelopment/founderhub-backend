from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from uuid import uuid4
from app.core.db import Base

class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    idea_id = Column(UUID(as_uuid=True))
    tokens_used = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
