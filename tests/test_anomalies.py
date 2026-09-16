import pytest
from app.services.anomaly_service import anomaly_service


def test_long_resolution_anomalies():
    """Verify statistical IQR anomaly detection on resolution times."""
    result = anomaly_service.scan_anomalies(anomaly_type="long_resolution_time")
    assert result.total == 21

    # Check each flagged ticket
    for item in result.anomalies:
        assert item.anomaly_type == "long_resolution_time"
        assert item.status == "Resolved"
        assert item.relevant_value is not None
        assert item.threshold is not None
        assert item.relevant_value > item.threshold


def test_unresolved_high_priority_aged():
    """Verify unresolved High and Critical tickets older than 24 hours."""
    result = anomaly_service.scan_anomalies(anomaly_type="unresolved_high_priority_aged")
    assert result.total == 80

    for item in result.anomalies:
        assert item.anomaly_type == "unresolved_high_priority_aged"
        assert item.priority in ("High", "Critical")
        assert item.status != "Resolved"
        assert item.relevant_value > 24.0


def test_low_customer_rating_anomalies():
    """Verify tickets with customer ratings <= 2 are flagged."""
    result = anomaly_service.scan_anomalies(anomaly_type="low_customer_rating")
    assert result.total == 47

    for item in result.anomalies:
        assert item.relevant_value in (1.0, 2.0)
        assert item.threshold == 2.0


def test_slow_response_anomalies():
    """Verify 95th percentile response time anomaly detection."""
    result = anomaly_service.scan_anomalies(anomaly_type="slow_response_time")
    assert result.total == 29

    for item in result.anomalies:
        assert item.relevant_value >= 4.8


def test_anomaly_filtering_by_severity():
    """Verify filtering anomalies by severity level."""
    res_crit = anomaly_service.scan_anomalies(severity="critical")
    for item in res_crit.anomalies:
        assert item.severity == "critical"


def test_anomaly_summary_distribution():
    """Verify summary breakdown accurately totals anomaly records."""
    result = anomaly_service.scan_anomalies()
    summary = result.summary

    sum_types = sum(summary.by_type.values())
    sum_severities = sum(summary.by_severity.values())

    assert summary.total_anomalies == sum_types
    assert summary.total_anomalies == sum_severities
