from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.ga import GASite, GAMetric, DecisionLogIn, GADecisionLog
from app.schemas.ga import GASiteOut, GACredentialsOut, GAMetricIn
from app.services.analytics.runner import run_ga_anomaly_analysis
from app.core.db import get_db

router = APIRouter(prefix="/api/ga", tags=["Google Analytics"])

@router.get("/sites", response_model=list[GASiteOut])
def get_all_sites(db: Session = Depends(get_db)):
    return db.query(GASite).all()

@router.get("/sites/{site_id}/credentials", response_model=GACredentialsOut)
def get_credentials(site_id: str, db: Session = Depends(get_db)):
    site = db.query(GASite).filter(GASite.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"ga4_credentials_json": site.ga4_credentials_json}

@router.post("/metrics")
def post_metrics(metric: GAMetricIn, db: Session = Depends(get_db)):
    db_metric = GAMetric(**metric.dict())
    db.add(db_metric)
    db.commit()
    return {"detail": "Metrics stored successfully"}

@router.post("/decisions")
def log_decision(decision: DecisionLogIn, db: Session = Depends(get_db)):
    log_entry = GADecisionLog(**decision.dict())
    db.add(log_entry)
    db.commit()
    return {"detail": "Decision log saved"}

@router.post("/analyze/{site_id}")
def analyze_ga_metrics(site_id: str, db: Session = Depends(get_db)):
    run_ga_anomaly_analysis(db, site_id)
    return {"detail": "GA metrics analyzed"}
    
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

    query = query.order_by(GAKPISnapshot.report_date.asc())
    return query.all()