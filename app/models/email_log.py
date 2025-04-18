from sqlalchemy import Column, String, Text, DateTime
from datetime import datetime
from app.core.db import Base

class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    to_email = Column(Text, nullable=False)
    subject = Column(Text, nullable=False)
    template_key = Column(Text)
    status = Column(Text, nullable=False)
    error = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
