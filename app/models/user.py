# SQLAlchemy Model (app/models/user.py)
from sqlalchemy import Column, String, Boolean, DateTime
from app.core.db import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, index=True)  # Using 36 for UUID strings
    tenant_id = Column(String(36), index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="user", nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"
