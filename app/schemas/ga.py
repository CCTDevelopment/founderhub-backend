from pydantic import BaseModel, UUID4
from datetime import date, datetime
from typing import Optional

class GASiteOut(BaseModel):
    id: UUID4
    tenant_id: UUID4
    site_name: str
    ga4_property_id: str

    class Config:
        from_attributes = True

class GACredentialsOut(BaseModel):
    ga4_credentials_json: str

class GAMetricIn(BaseModel):
    site_id: UUID4
    tenant_id: UUID4
    property_id: str
    report_date: date
    session_source: Optional[str]
    bounce_rate: Optional[float]
    conversion_rate: Optional[float]
    avg_session_duration: Optional[float]
    pages_per_session: Optional[float]

class DecisionLogIn(BaseModel):
    timestamp: datetime
    agent: str
    kpi: str
    current: float
    average: float
    std_dev: float
    status: str
    reason: str

class KPISnapshotOut(BaseModel):
    site_id: UUID4
    kpi_name: str
    value: Optional[float]
    report_date: date

    class Config:
        from_attributes = True
