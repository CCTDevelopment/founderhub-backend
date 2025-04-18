from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import UUID
from app.core.base import Base
import uuid

class SparringTemplate(Base):
    __tablename__ = "sparring_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(Text, nullable=False, unique=True)
    template_text = Column(Text, nullable=False)
