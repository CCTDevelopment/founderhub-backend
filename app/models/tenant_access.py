from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from datetime import datetime
from app.core.db import Base

class TenantAccessGrant(Base):
    __tablename__ = "tenant_access_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    granted_to = Column(UUID(as_uuid=True), nullable=False)
    granted_by = Column(UUID(as_uuid=True), nullable=False)
    reason = Column(String)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
