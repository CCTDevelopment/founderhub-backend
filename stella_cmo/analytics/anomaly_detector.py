import numpy as np

class AnomalyDetector:
    def __init__(self, threshold_std_dev=2):
        self.threshold = threshold_std_dev

    def detect(self, kpi_list):
        if len(kpi_list) < 3:
            return None  # Not enough data to detect anomalies

        current = kpi_list[-1]
        historical = kpi_list[:-1]

        avg = np.mean(historical)
        std_dev = np.std(historical)

        deviation = abs(current - avg)

        if deviation > self.threshold * std_dev:
            return {
                "current": current,
                "average": avg,
                "std_dev": std_dev,
                "status": "anomaly_detected"
            }

        return {
            "current": current,
            "average": avg,
            "std_dev": std_dev,
            "status": "normal"
        }
