from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from datetime import datetime
from app.core.db import Base

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
