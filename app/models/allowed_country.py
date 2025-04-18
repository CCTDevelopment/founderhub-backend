from sqlalchemy import Column, String, DateTime, ForeignKey
from app.core.db import Base
from datetime import datetime

class AllowedCountry(Base):
    __tablename__ = "allowed_countries"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    country_code = Column(String(4), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
