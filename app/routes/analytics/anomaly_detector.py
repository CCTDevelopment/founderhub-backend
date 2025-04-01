import numpy as np
import uuid
from datetime import datetime
from app.core.db import get_db

class AnomalyDetector:
    """
    Detects anomalies based on the standard deviation threshold and logs detailed results to SQL.
    """

    def __init__(self, threshold_std_dev: float = 2):
        self.threshold = threshold_std_dev

    def detect(self, kpi_list: list[float]) -> dict | None:
        """
        Compute anomaly details from a list of KPI values.
        Returns a dictionary with detailed metrics if enough data exists,
        otherwise returns None.
        """
        if len(kpi_list) < 3:
            return None  # Not enough data to detect anomalies

        current = kpi_list[-1]
        historical = kpi_list[:-1]

        avg = np.mean(historical)
        std_dev = np.std(historical)
        deviation = abs(current - avg)
        threshold_value = self.threshold * std_dev

        result = {
            "current": current,
            "average": avg,
            "std_dev": std_dev,
            "deviation": deviation,
            "threshold": threshold_value,
            "status": "anomaly_detected" if deviation > threshold_value else "normal"
        }

        return result

    async def store_decision_log(self, agent: str, kpi: str, result: dict, reason: str = "") -> None:
        """
        Stores the anomaly detection details into the SQL table (ga_decision_logs).
        Expected table columns:
            id, timestamp, agent, kpi, current, average, std_dev, status, reason
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
