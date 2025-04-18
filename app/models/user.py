from sqlalchemy import Column, String, Boolean, DateTime
from datetime import datetime

from app.core.db import Base  # ✅ This is what was missing!

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), index=True, nullable=False)

    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

    name = Column(String(255), nullable=True)  # ✅ Now present
    role = Column(String(50), nullable=False, default="user")
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ✅ Login and region tracking
    allow_new_region_login = Column(Boolean, default=False)  # ❌ Disallow new regions by default
    allow_admin_alerts = Column(Boolean, default=True)       # ✅ Admin gets notified by default
    last_login_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<User id={self.id} email={self.email} role={self.role}>"
