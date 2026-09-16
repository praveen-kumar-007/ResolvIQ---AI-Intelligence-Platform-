from datetime import datetime
import logging
from typing import Dict, List, Optional
import pandas as pd

from app.core.config import get_settings
from app.models.schemas import AnomalyItem, AnomalyListResponse, AnomalySummaryResponse
from app.services.data_service import DataService, data_service

logger = logging.getLogger(__name__)


class AnomalyService:
    """Detects and categorizes ticket anomalies using statistical and rule-based methods."""

    def __init__(self, data_svc: Optional[DataService] = None):
        self.data_service = data_svc or data_service
        self.settings = get_settings()

    def scan_anomalies(
        self,
        severity: Optional[str] = None,
        anomaly_type: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
    ) -> AnomalyListResponse:
        """Run all anomaly detection engines and return aggregated results with optional filtering."""
        df = self.data_service.get_all_dataframe()
        if df.empty:
            return AnomalyListResponse(
                total=0,
                summary=AnomalySummaryResponse(total_anomalies=0, by_type={}, by_severity={}, by_priority={}),
                anomalies=[]
            )

        all_anomalies: List[AnomalyItem] = []

        # 1. Long Resolution Time (Statistical IQR)
        all_anomalies.extend(self._detect_long_resolution_anomalies(df))

        # 2. Unresolved High-Priority Tickets > 24 Hours
        all_anomalies.extend(self._detect_unresolved_high_priority_anomalies(df))

        # 3. Slow Response Time (Statistical High Percentile)
        all_anomalies.extend(self._detect_slow_response_anomalies(df))

        # 4. Low Customer Rating (<= 2)
        all_anomalies.extend(self._detect_low_rating_anomalies(df))

        # Apply optional filters
        filtered = all_anomalies
        if severity:
            filtered = [a for a in filtered if a.severity.lower() == severity.lower()]
        if anomaly_type:
            filtered = [a for a in filtered if a.anomaly_type.lower() == anomaly_type.lower()]
        if priority:
            filtered = [a for a in filtered if a.priority.lower() == priority.lower()]
        if category:
            filtered = [a for a in filtered if a.category and a.category.lower() == category.lower()]

        # Generate summary distributions
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        by_priority: Dict[str, int] = {}

        for item in filtered:
            by_type[item.anomaly_type] = by_type.get(item.anomaly_type, 0) + 1
            by_severity[item.severity] = by_severity.get(item.severity, 0) + 1
            by_priority[item.priority] = by_priority.get(item.priority, 0) + 1

        summary = AnomalySummaryResponse(
            total_anomalies=len(filtered),
            by_type=by_type,
            by_severity=by_severity,
            by_priority=by_priority
        )

        return AnomalyListResponse(
            total=len(filtered),
            summary=summary,
            anomalies=filtered
        )

    def _detect_long_resolution_anomalies(self, df: pd.DataFrame) -> List[AnomalyItem]:
        """Detect resolved tickets with resolution times exceeding the statistical IQR upper bound."""
        anomalies: List[AnomalyItem] = []
        resolved_with_time = df[df["resolution_time_hrs"].notna() & (df["status"] == "Resolved")].copy()

        if resolved_with_time.empty:
            return anomalies

        resol_series = resolved_with_time["resolution_time_hrs"].astype(float)
        q1 = resol_series.quantile(0.25)
        q3 = resol_series.quantile(0.75)
        iqr = q3 - q1
        multiplier = self.settings.anomaly_resolution_iqr_multiplier
        upper_threshold = round(float(q3 + multiplier * iqr), 2)
        extreme_threshold = round(float(q3 + 3.0 * iqr), 2)

        outliers = resolved_with_time[resol_series > upper_threshold]

        for _, row in outliers.iterrows():
            val = float(row["resolution_time_hrs"])
            severity = "critical" if val >= extreme_threshold else "high"
            anomalies.append(
                AnomalyItem(
                    ticket_id=str(row["ticket_id"]),
                    anomaly_type="long_resolution_time",
                    severity=severity,
                    description=f"Resolution time of {val:.1f} hrs exceeds statistical upper bound of {upper_threshold:.1f} hrs (IQR={iqr:.1f}).",
                    relevant_value=round(val, 2),
                    threshold=upper_threshold,
                    created_at=str(row["created_at"]),
                    priority=str(row["priority"]),
                    status=str(row["status"]),
                    agent_id=str(row["agent_id"]),
                    category=str(row.get("category", "General"))
                )
            )

        return anomalies

    def _detect_unresolved_high_priority_anomalies(self, df: pd.DataFrame) -> List[AnomalyItem]:
        """Detect High or Critical priority tickets that remain unresolved beyond 24 hours."""
        anomalies: List[AnomalyItem] = []
        now = datetime.now()

        unresolved_high = df[
            (df["priority"].isin(["High", "Critical"])) &
            (df["status"] != "Resolved")
        ].copy()

        for _, row in unresolved_high.iterrows():
            try:
                created_dt = pd.to_datetime(row["created_at"])
                age_hours = (now - created_dt).total_seconds() / 3600.0
            except Exception:
                age_hours = 999.0

            if age_hours > 24.0:
                severity = "critical" if row["priority"] == "Critical" else "high"
                anomalies.append(
                    AnomalyItem(
                        ticket_id=str(row["ticket_id"]),
                        anomaly_type="unresolved_high_priority_aged",
                        severity=severity,
                        description=f"{row['priority']} priority ticket has remained {row['status']} for over 24 hours ({age_hours:.1f} hrs).",
                        relevant_value=round(age_hours, 1),
                        threshold=24.0,
                        created_at=str(row["created_at"]),
                        priority=str(row["priority"]),
                        status=str(row["status"]),
                        agent_id=str(row["agent_id"]),
                        category=str(row.get("category", "General"))
                    )
                )

        return anomalies

    def _detect_slow_response_anomalies(self, df: pd.DataFrame) -> List[AnomalyItem]:
        """Detect tickets with initial response times exceeding the statistical 95th percentile."""
        anomalies: List[AnomalyItem] = []
        valid_resp = df[df["response_time_hrs"].notna()].copy()
        if valid_resp.empty:
            return anomalies

        resp_series = valid_resp["response_time_hrs"].astype(float)
        p_threshold = float(resp_series.quantile(self.settings.anomaly_response_percentile / 100.0))
        p_threshold = round(p_threshold, 2)

        slow_tickets = valid_resp[resp_series >= p_threshold]

        for _, row in slow_tickets.iterrows():
            val = float(row["response_time_hrs"])
            anomalies.append(
                AnomalyItem(
                    ticket_id=str(row["ticket_id"]),
                    anomaly_type="slow_response_time",
                    severity="medium",
                    description=f"Response time of {val:.1f} hrs ranks in the worst {100 - self.settings.anomaly_response_percentile:.0f}% (>={p_threshold:.1f} hrs).",
                    relevant_value=round(val, 2),
                    threshold=p_threshold,
                    created_at=str(row["created_at"]),
                    priority=str(row["priority"]),
                    status=str(row["status"]),
                    agent_id=str(row["agent_id"]),
                    category=str(row.get("category", "General"))
                )
            )

        return anomalies

    def _detect_low_rating_anomalies(self, df: pd.DataFrame) -> List[AnomalyItem]:
        """Detect resolved tickets with customer satisfaction ratings <= 2."""
        anomalies: List[AnomalyItem] = []
        low_rated = df[df["customer_rating"].notna() & (df["customer_rating"].astype(float) <= 2.0)].copy()

        for _, row in low_rated.iterrows():
            rating = int(float(row["customer_rating"]))
            severity = "high" if rating == 1 else "medium"
            anomalies.append(
                AnomalyItem(
                    ticket_id=str(row["ticket_id"]),
                    anomaly_type="low_customer_rating",
                    severity=severity,
                    description=f"Customer assigned dissatisfied rating of {rating}/5 for resolved issue.",
                    relevant_value=float(rating),
                    threshold=2.0,
                    created_at=str(row["created_at"]),
                    priority=str(row["priority"]),
                    status=str(row["status"]),
                    agent_id=str(row["agent_id"]),
                    category=str(row.get("category", "General"))
                )
            )

        return anomalies


# Singleton helper instance
anomaly_service = AnomalyService()
