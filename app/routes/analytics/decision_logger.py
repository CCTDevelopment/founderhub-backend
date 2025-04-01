import uuid
from datetime import datetime
from app.core.db import get_db

async def log_decision(agent: str, kpi: str, result: dict, reason: str) -> None:
    """
    Logs detailed anomaly detection metrics into the SQL table 'ga_decision_logs'.
    
    The expected table schema includes the following columns:
        - id: UUID
        - timestamp: TIMESTAMP
        - agent: String
        - kpi: String
        - current: Float
        - average: Float
        - std_dev: Float
        - status: String
        - reason: String
    """
    db = await get_db()
    await db.execute(
        """
        INSERT INTO ga_decision_logs (
            id, timestamp, agent, kpi, current, average, std_dev, status, reason
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        str(uuid.uuid4()),
        datetime.utcnow(),
        agent,
        kpi,
        result["current"],
        result["average"],
        result["std_dev"],
        result["status"],
        reason
    )
