import numpy as np
from typing import List, Optional, Dict, Union

class AnomalyDetector:
    """
    Detects anomalies in KPI data using standard deviation threshold.
    """

    def __init__(self, threshold_std_dev: float = 2.0):
        """
        :param threshold_std_dev: Number of standard deviations from the mean to consider as an anomaly.
        """
        self.threshold = threshold_std_dev

    def detect(self, kpi_list: List[Union[int, float]]) -> Optional[Dict[str, Union[str, float]]]:
        """
        Detect anomalies in a list of KPI values.

        :param kpi_list: List of historical KPI values including the most recent one last.
        :return: A dictionary with analysis result or None if not enough data.
        """
        if len(kpi_list) < 3:
            return None  # Not enough data to detect anomalies

        current = kpi_list[-1]
        historical = kpi_list[:-1]

        average = float(np.mean(historical))
        std_dev = float(np.std(historical))
        deviation = abs(current - average)

        status = "anomaly_detected" if deviation > self.threshold * std_dev else "normal"

        return {
            "current": current,
            "average": average,
            "std_dev": std_dev,
            "status": status
        }
