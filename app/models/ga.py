from sqlalchemy import Column, String, Float, Date, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db import Base
import uuid

class GASite(Base):
    __tablename__ = "ga_sites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    site_name = Column(String, nullable=False)
    ga4_property_id = Column(String, nullable=False)
    ga4_credentials_json = Column(String, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


class GAMetric(Base):
    __tablename__ = "ga_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("ga_sites.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    property_id = Column(String, nullable=False)
    report_date = Column(Date, nullable=False)
    session_source = Column(String, nullable=True)
    bounce_rate = Column(Float, nullable=True)
    conversion_rate = Column(Float, nullable=True)
    avg_session_duration = Column(Float, nullable=True)
    pages_per_session = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())

class GADecisionLog(Base):
    __tablename__ = "ga_decision_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(TIMESTAMP, nullable=False)
    agent = Column(String, nullable=False)
    kpi = Column(String, nullable=False)
    current = Column(Float, nullable=False)
    average = Column(Float, nullable=False)
    std_dev = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    reason = Column(String, nullable=False)

class GAKPISnapshot(Base):
    __tablename__ = "ga_kpi_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("ga_sites.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    property_id = Column(String, nullable=False)
    kpi_name = Column(String, nullable=False)
    value = Column(Float, nullable=True)
    report_date = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
