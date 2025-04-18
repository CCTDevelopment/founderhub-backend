from sqlalchemy.orm import Session
from datetime import datetime
from app.models.ga import GAMetric, GADecisionLog
from app.services.analytics.anomaly_detector import AnomalyDetector
from app.services.analytics.logging import log_decision

def run_ga_anomaly_analysis(db: Session, site_id: str):
    detector = AnomalyDetector(threshold_std_dev=2)

    kpi_fields = [
        ("bounce_rate", "Bounce Rate"),
        ("conversion_rate", "Conversion Rate"),
        ("avg_session_duration", "Avg Session Duration"),
        ("pages_per_session", "Pages Per Session")
    ]

    for field_name, label in kpi_fields:
        values = (
            db.query(getattr(GAMetric, field_name))
            .filter(GAMetric.site_id == site_id)
            .order_by(GAMetric.report_date.desc())
            .limit(10)
            .all()
        )

        kpi_values = [v[0] for v in reversed(values) if v[0] is not None]
        result = detector.detect(kpi_values)

        if not result:
            continue

        reason = f"{label} value is {result['current']} with average {result['average']} ± {result['std_dev']}"
        
        log = GADecisionLog(
            timestamp=datetime.utcnow(),
            agent="ga-analyzer",
            kpi=field_name,
            current=result["current"],
            average=result["average"],
            std_dev=result["std_dev"],
            status=result["status"],
            reason=reason,
        )
        db.add(log)

        # Optionally use your custom logger
        log_decision(db, agent="ga-analyzer", kpi=field_name, result=result, reason=reason)

    db.commit()
    print(f"✅ GA analysis complete for site {site_id}")
