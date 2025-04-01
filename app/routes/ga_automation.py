from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import date

# Import your GA models and schemas
from app.models.ga import GASite, GAMetric, GADecisionLog, GAKPISnapshot
from app.schemas.ga import GASiteOut, GACredentialsOut, GAMetricIn, KPISnapshotOut, DecisionLogIn
from app.services.analytics.runner import run_ga_anomaly_analysis
from app.core.db import get_db

router = APIRouter(prefix="/api/ga", tags=["Google Analytics"])

# Endpoint: Get all GA sites
@router.get("/sites", response_model=List[GASiteOut])
def get_all_sites(db: Session = Depends(get_db)):
    sites = db.query(GASite).all()
    return sites

# Endpoint: Get GA credentials for a site
@router.get("/sites/{site_id}/credentials", response_model=GACredentialsOut)
def get_credentials(site_id: str, db: Session = Depends(get_db)):
    site = db.query(GASite).filter(GASite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"ga4_credentials_json": site.ga4_credentials_json}

# Endpoint: Store GA metrics
@router.post("/metrics")
def post_metrics(metric: GAMetricIn, db: Session = Depends(get_db)):
    db_metric = GAMetric(**metric.dict())
    db.add(db_metric)
    db.commit()
    return {"detail": "Metrics stored successfully"}

# Endpoint: Log decision based on GA analysis
@router.post("/decisions")
def log_decision(decision: DecisionLogIn, db: Session = Depends(get_db)):
    log_entry = GADecisionLog(**decision.dict())
    db.add(log_entry)
    db.commit()
    return {"detail": "Decision log saved"}

# Endpoint: Analyze GA metrics (e.g., run anomaly detection)
@router.post("/analyze/{site_id}")
def analyze_ga_metrics(site_id: str, db: Session = Depends(get_db)):
    run_ga_anomaly_analysis(db, site_id)
    return {"detail": "GA metrics analyzed"}

# Endpoint: Retrieve KPI snapshots
@router.get("/kpis", response_model=List[KPISnapshotOut])
def get_kpi_snapshots(
    site_id: UUID,
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
    query = query.order_by(GAKPISnapshot.report_date.asc())
    return query.all()

# Endpoint: Trigger a generic automation action
@router.post("/trigger-action/{site_id}")
def trigger_automation_action(site_id: str, action: str, db: Session = Depends(get_db)):
    """
    Triggers an automated action (like posting ads or updating social media) based on GA data.
    The 'action' parameter can be used to specify which action to trigger.
    """
    # Placeholder: Here you can call external services based on GA insights.
    return {"detail": f"Automation action '{action}' triggered for site {site_id}"}

# Endpoint: Auto-adjust ads based on ad traffic KPI
@router.post("/auto-adjust-ads/{site_id}")
def auto_adjust_ads(site_id: str, threshold: float = Query(100.0), db: Session = Depends(get_db)):
    """
    Checks the latest 'ad_traffic' KPI and, if below the threshold, triggers an ad adjustment.
    """
    kpi = db.query(GAKPISnapshot).filter(
        GAKPISnapshot.site_id == site_id,
        GAKPISnapshot.kpi_name == "ad_traffic"
    ).order_by(GAKPISnapshot.report_date.desc()).first()
    
    if not kpi:
        raise HTTPException(status_code=404, detail="No 'ad_traffic' KPI found")
    
    ad_traffic = kpi.value
    if ad_traffic < threshold:
        # Here, you might log a decision, call an external service to adjust ads, etc.
        # For demonstration, we trigger a generic action.
        action_response = {
            "detail": f"Ad traffic ({ad_traffic}) below threshold ({threshold}). Ad adjustment triggered."
        }
        # Optionally, log this decision:
        decision_data = {
            "site_id": site_id,
            "agent": "System",
            "kpi": "ad_traffic",
            "current": ad_traffic,
            "average": threshold,  # Using threshold as a proxy for desired performance
            "std_dev": 0.0,
            "status": "adjustment_triggered",
            "reason": "Ad traffic below threshold"
        }
        # You can store this decision log using your /decisions endpoint logic
        db_decision = GADecisionLog(**decision_data)
        db.add(db_decision)
        db.commit()
        return action_response
    else:
        return {"detail": f"Ad traffic ({ad_traffic}) meets or exceeds threshold ({threshold}). No adjustment needed."}
