from datetime import datetime
from sqlalchemy.orm import Session
from app.models.ga import GADecisionLog

def log_decision(
    db: Session,
    agent: str,
    kpi: str,
    result: dict,
    reason: str
) -> None:
    """
    Stores the decision analysis result into the database.
    """
    log_entry = GADecisionLog(
        timestamp=datetime.utcnow(),
        agent=agent,
        kpi=kpi,
        current=result["current"],
        average=result["average"],
        std_dev=result["std_dev"],
        status=result["status"],
        reason=reason
    )

    db.add(log_entry)
    db.commit()
    print(f"✅ Logged decision: {kpi} ({result['status']})")
