from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from app.core.db import Base
import uuid

class LoginEvent(Base):
    __tablename__ = "login_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ip_address = Column(String)
    location = Column(String)
    country = Column(String)
    user_agent = Column(String)
    is_new_ip = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
