from __future__ import annotations

import asyncio

from app.config import settings
from app.prom import PrometheusClient


def verify_recovery(before: dict, after: dict, origin: str) -> dict:
    b = before.get(origin) or {}
    a = after.get(origin) or {}
    p95_before = b.get("p95_ms") or 0
    p95_after = a.get("p95_ms") or 0
    err_before = b.get("error_rate") or 0
    err_after = a.get("error_rate") or 0
    health_after = a.get("health")
    if health_after is None:
        health_after = 1
    p95_ok = p95_after <= settings.latency_p95_threshold_ms or (
        p95_before > 0 and p95_after <= p95_before * 0.5
    )
    err_ok = err_after <= settings.error_rate_threshold or (
        err_before > 0 and err_after <= err_before * 0.4
    )
    health_ok = health_after >= 1
    if p95_ok and err_ok and health_ok:
        status = "RESOLVED"
    elif health_ok and (p95_ok or err_ok):
        status = "PARTIALLY_RESOLVED"
    else:
        status = "FAILED"
    return {
        "status": status,
        "before": {"p95_ms": p95_before, "error_rate": err_before},
        "after": {"p95_ms": p95_after, "error_rate": err_after, "health": health_after},
        "checks": {"p95_ok": p95_ok, "err_ok": err_ok, "health_ok": health_ok},
        "samples_used": 1,
        "recovery_percentage": round(100 * sum((p95_ok, err_ok, health_ok)) / 3, 1),
    }


async def verify_stabilized(before: dict, origin: str, *, prom: PrometheusClient | None = None, samples: int | None = None, interval: float | None = None) -> dict:
    """Require several real telemetry observations before declaring recovery."""
    client = prom or PrometheusClient()
    total = samples or settings.verification_samples
    delay = settings.verification_sample_interval_seconds if interval is None else interval
    observations: list[dict] = []
    for index in range(max(1, total)):
        snapshot = await client.snapshot()
        observations.append(snapshot.get(origin) or {})
        if index + 1 < total and delay > 0:
            await asyncio.sleep(delay)
    after = observations[-1] if observations else {}
    individual = [verify_recovery(before, {origin: item}, origin) for item in observations]
    recovered = sum(1 for item in individual if item["status"] == "RESOLVED")
    partial = sum(1 for item in individual if item["status"] == "PARTIALLY_RESOLVED")
    if recovered == len(individual):
        status = "RESOLVED"
    elif recovered + partial:
        status = "PARTIALLY_RESOLVED"
    else:
        status = "FAILED"
    final = verify_recovery(before, {origin: after}, origin)
    final.update({"status": status, "samples_used": len(observations), "recovery_percentage": round(100 * recovered / len(observations), 1) if observations else 0, "samples": observations})
    return final
