from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID as UUID4
from datetime import datetime, date

# Models
from app.models.ga import GASite, GAMetric, GADecisionLog, GAKPISnapshot

# Schemas
from app.schemas.ga import (
    GASiteOut,
    GACredentialsOut,
    GAMetricIn,
    DecisionLogIn,
    KPISnapshotOut
)

# Services
from app.services.analytics.runner import run_ga_anomaly_analysis

# DB session
from app.core.session import get_db

router = APIRouter(prefix="/api/ga", tags=["Google Analytics"])

# --- GA Site Management ---

@router.get("/sites", response_model=List[GASiteOut])
def get_all_sites(db: Session = Depends(get_db)):
    return db.query(GASite).all()


@router.get("/sites/{site_id}/credentials", response_model=GACredentialsOut)
def get_credentials(site_id: UUID4, db: Session = Depends(get_db)):
    site = db.query(GASite).filter(GASite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"ga4_credentials_json": site.ga4_credentials_json}

# --- GA Metrics ---

@router.post("/metrics")
def post_metrics(metric: GAMetricIn, db: Session = Depends(get_db)):
    db_metric = GAMetric(**metric.model_dump())  # Use model_dump for Pydantic v2
    db.add(db_metric)
    db.commit()
    return {"detail": "Metrics stored successfully"}

# --- GA Decision Logs ---

@router.post("/decisions")
def log_decision(decision: DecisionLogIn, db: Session = Depends(get_db)):
    db_log = GADecisionLog(**decision.model_dump())
    db.add(db_log)
    db.commit()
    return {"detail": "Decision log saved"}

# --- Run Analysis ---

@router.post("/analyze/{site_id}")
def analyze_ga_metrics(site_id: UUID4, db: Session = Depends(get_db)):
    run_ga_anomaly_analysis(db, site_id)
    return {"detail": "GA metrics analyzed"}

# --- KPI Snapshot ---

@router.get("/kpis", response_model=List[KPISnapshotOut])
def get_kpi_snapshots(
    site_id: UUID4,
    kpi_name: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(GAKPISnapshot).filter(
        GAKPISnapshot.site_id == site_id,
        GAKPISnapshot.kpi_name == kpi_name
    )

    if start_date:
        query = query.filter(GAKPISnapshot.report_date >= start_date)
    if end_date:
        query = query.filter(GAKPISnapshot.report_date <= end_date)

    return query.order_by(GAKPISnapshot.report_date.asc()).all()
