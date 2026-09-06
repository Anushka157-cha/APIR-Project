from __future__ import annotations

import math
from typing import Any


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    return max(min_val, min(max_val, value))


def compute_incident_fingerprint(service: str, incident_type: str, primary_metric: str = "p95_ms") -> str:
    """Generate a deterministic fingerprint for incident categorization and recurrence tracking."""
    clean_service = (service or "unknown").strip().lower()
    clean_type = (incident_type or "unknown").strip().lower()
    clean_metric = (primary_metric or "p95_ms").strip().lower()
    return f"{clean_service}:{clean_type}:{clean_metric}"


def calculate_anomaly_score(
    metrics: dict[str, Any],
    baseline: dict[str, list[float]] | None = None,
    findings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Deterministically calculate anomaly score [0.0, 1.0] and exact contributing factors
    from real Prometheus observations and collected baselines.
    """
    baseline = baseline or {}
    findings = findings or []

    p95 = float(metrics.get("p95_ms") or 0.0)
    err = float(metrics.get("error_rate") or 0.0)
    rps = float(metrics.get("rps") or 0.0)
    health = metrics.get("health")
    if health is None:
        health = 1.0
    else:
        health = float(health)

    # Baselines
    p95_samples = [x for x in baseline.get("p95_ms", []) if isinstance(x, (int, float))]
    base_p95 = sum(p95_samples) / len(p95_samples) if p95_samples else 200.0
    
    err_samples = [x for x in baseline.get("error_rate", []) if isinstance(x, (int, float))]
    base_err = sum(err_samples) / len(err_samples) if err_samples else 0.0

    # Latency signal: ratio of excess latency above baseline
    lat_delta = max(0.0, p95 - base_p95)
    lat_signal = clamp(lat_delta / max(base_p95 * 2.0, 400.0))

    # Error signal: error rate relative to failure threshold
    err_signal = clamp(err / 0.4)

    # Health signal: 1.0 if crashed / unreachable, 0.0 if healthy
    health_signal = 1.0 if health <= 0 else 0.0

    # Statistical variance signal (Z-score from baseline samples)
    if len(p95_samples) >= 2:
        variance = sum((x - base_p95) ** 2 for x in p95_samples) / (len(p95_samples) - 1)
        stdev = math.sqrt(variance)
        z_val = max(0.0, (p95 - base_p95) / stdev) if stdev > 0 else 0.0
    else:
        z_val = 2.5 if "latency_zscore" in findings else 0.0
    z_signal = clamp(z_val / 5.0)

    # Database / Dependency signal from findings
    db_signal = 0.8 if "database_latency" in findings or "database_failure" in findings else 0.0

    # Weighted composite score
    weights = {
        "p95_latency": 0.35,
        "error_rate": 0.25,
        "service_health": 0.20,
        "z_score_deviation": 0.10,
        "database_dependency": 0.10,
    }

    raw_score = (
        weights["p95_latency"] * lat_signal
        + weights["error_rate"] * err_signal
        + weights["service_health"] * health_signal
        + weights["z_score_deviation"] * z_signal
        + weights["database_dependency"] * db_signal
    )

    # If service is crashed, the incident is inherently critical
    if health_signal == 1.0:
        raw_score = max(raw_score, 0.90)
    elif lat_signal > 0.8:
        raw_score = max(raw_score, 0.75)

    final_score = round(clamp(raw_score), 3)

    contributors = {
        "p95_latency": round(weights["p95_latency"] * lat_signal, 3),
        "error_rate": round(weights["error_rate"] * err_signal, 3),
        "service_health": round(weights["service_health"] * health_signal, 3),
        "z_score_deviation": round(weights["z_score_deviation"] * z_signal, 3),
        "database_dependency": round(weights["database_dependency"] * db_signal, 3),
    }

    # Observed vs Baseline summary
    pct_deviation = round(((p95 - base_p95) / base_p95) * 100.0, 1) if base_p95 > 0 else 0.0
    abs_deviation = round(p95 - base_p95, 2)

    return {
        "anomaly_score": final_score,
        "contributors": contributors,
        "weights": weights,
        "observed_value": round(p95, 2),
        "baseline_value": round(base_p95, 2),
        "absolute_deviation": abs_deviation,
        "percentage_deviation": pct_deviation,
        "error_rate": round(err, 4),
        "request_rate": round(rps, 2),
        "z_score": round(z_val, 2),
        "service_health": health,
    }


def build_intelligence_record(
    service: str,
    incident_type: str,
    metrics: dict[str, Any],
    findings: list[str],
    baseline: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """Construct full incident intelligence record persisted with the incident."""
    primary_metric = "error_rate" if "error" in incident_type else "p95_ms"
    fingerprint = compute_incident_fingerprint(service, incident_type, primary_metric)
    anomaly_data = calculate_anomaly_score(metrics, baseline, findings)

    explanation = (
        f"Incident created for {service} because {primary_metric} ({anomaly_data['observed_value']}) "
        f"exceeded baseline ({anomaly_data['baseline_value']}) by {anomaly_data['percentage_deviation']}% "
        f"(z-score: {anomaly_data['z_score']}, findings: {', '.join(findings)})."
    )

    return {
        "affected_service": service,
        "incident_type": incident_type,
        "fingerprint": fingerprint,
        "primary_metric": primary_metric,
        "explanation": explanation,
        "findings": findings,
        **anomaly_data,
    }
