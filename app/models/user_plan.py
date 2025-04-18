from sqlalchemy import Column, String, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from app.core.db import Base

class UserPlan(Base):
    __tablename__ = "user_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String, nullable=False, unique=True)         # e.g., "freedum", "basic", etc.
    max_tokens = Column(Integer, nullable=False)               # Monthly token cap
    price_usd = Column(Float, nullable=False)                  # e.g., $5.00
    cost_per_1k_tokens = Column(Float, default=0.01)           # OpenAI pricing baseline
