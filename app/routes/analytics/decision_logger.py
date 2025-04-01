import json
from datetime import datetime
import os

def log_decision(agent, kpi, result, reason):
    log = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent,
        "kpi": kpi,
        "current": result["current"],
        "average": result["average"],
        "std_dev": result["std_dev"],
        "status": result["status"],
        "reason": reason
    }

    os.makedirs("logs", exist_ok=True)
    with open("logs/decision_logs.json", "a") as f:
        f.write(json.dumps(log) + "\n")
