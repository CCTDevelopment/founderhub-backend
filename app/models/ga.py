from sqlalchemy import Column, String, Float, Date, ForeignKey, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core import Base
import uuid

class GASite(Base):
    __tablename__ = "ga_sites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    site_name = Column(String, nullable=False)
    ga4_property_id = Column(String, nullable=False)
    ga4_credentials_json = Column(String, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<GASite(id={self.id}, site_name='{self.site_name}')>"

class GAMetric(Base):
    __tablename__ = "ga_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("ga_sites.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    property_id = Column(String, nullable=False)
    report_date = Column(Date, nullable=False)
    session_source = Column(String, nullable=True)
    bounce_rate = Column(Float, nullable=True)
    conversion_rate = Column(Float, nullable=True)
    avg_session_duration = Column(Float, nullable=True)
    pages_per_session = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<GAMetric(id={self.id}, report_date={self.report_date})>"

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

    def __repr__(self):
        return f"<GADecisionLog(id={self.id}, kpi='{self.kpi}', status='{self.status}')>"

class GAKPISnapshot(Base):
    __tablename__ = "ga_kpi_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("ga_sites.id"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    property_id = Column(String, nullable=False)
    kpi_name = Column(String, nullable=False)
    value = Column(Float, nullable=True)
    report_date = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<GAKPISnapshot(id={self.id}, kpi_name='{self.kpi_name}', value={self.value})>"
