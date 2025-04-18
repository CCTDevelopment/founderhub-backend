from sqlalchemy import Column, Text, String, DateTime
from app.core.db import Base
from datetime import datetime
import uuid

class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    template_key = Column(String(50), unique=True, nullable=False)  # ✅ matches DB column name
    subject = Column(Text, nullable=False)
    html = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
