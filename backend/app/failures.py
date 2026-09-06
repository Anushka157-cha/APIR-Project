from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as redis

from app.config import settings

SCENARIOS: dict[str, dict] = {
    "FAIL_PAYMENT_LATENCY": {
        "description": "Add 2000ms delay to payment-service handlers",
        "target": "payment-service",
        "flags": {"payment-service": {"latency_ms": "2000", "latency_jitter_ms": "200"}},
        "expected_root_cause": "payment service injected or handler latency",
        "expected_affected": ["payment-service", "order-service", "gateway"],
        "expected_remediation": "restart_service",
        "severity": "HIGH",
    },
    "FAIL_PAYMENT_ERRORS": {
        "description": "Inject 50% 5xx on payment-service",
        "target": "payment-service",
        "flags": {"payment-service": {"error_rate": "0.5", "error_status": "500"}},
        "expected_root_cause": "high injected error rate",
        "expected_affected": ["payment-service", "order-service", "gateway"],
        "expected_remediation": "restart_service",
        "severity": "HIGH",
    },
    "FAIL_PAYMENT_CRASH": {
        "description": "Crash payment-service (503)",
        "target": "payment-service",
        "flags": {"payment-service": {"crash": "1"}},
        "expected_root_cause": "payment service injected or handler latency",
        "expected_affected": ["payment-service", "order-service", "gateway"],
        "expected_remediation": "restart_service",
        "severity": "CRITICAL",
    },
    "FAIL_INVENTORY_CRASH": {
        "description": "Crash inventory-service",
        "target": "inventory-service",
        "flags": {"inventory-service": {"crash": "1"}},
        "expected_root_cause": "inventory service crash",
        "expected_affected": ["inventory-service", "order-service", "gateway"],
        "expected_remediation": "restart_service",
        "severity": "CRITICAL",
    },
    "FAIL_DATABASE": {
        "description": "Disable database access on payment-service",
        "target": "payment-service",
        "flags": {"payment-service": {"db_disabled": "1"}},
        "expected_root_cause": "database unavailable",
        "expected_affected": ["payment-service", "order-service"],
        "expected_remediation": "restart_service",
        "severity": "CRITICAL",
    },
    "FAIL_DATABASE_LATENCY": {
        "description": "Add database latency on payment-service",
        "target": "payment-service",
        "flags": {"payment-service": {"db_latency_ms": "1500"}},
        "expected_root_cause": "database unavailable",
        "expected_affected": ["payment-service"],
        "expected_remediation": "restart_service",
        "severity": "HIGH",
    },
    "FAIL_NETWORK_LATENCY": {
        "description": "Add delay on gateway and order-service",
        "target": "gateway",
        "flags": {
            "gateway": {"latency_ms": "800"},
            "order-service": {"latency_ms": "800"},
        },
        "expected_root_cause": "network latency between services",
        "expected_affected": ["gateway", "order-service"],
        "expected_remediation": "rollback_service",
        "severity": "MEDIUM",
    },
    "FAIL_CONNECTION_POOL": {
        "description": "Simulate connection pool exhaustion on payment-service",
        "target": "payment-service",
        "flags": {"payment-service": {"pool_exhaust": "1", "pool_wait_s": "1.6"}},
        "expected_root_cause": "database connection pool exhaustion",
        "expected_affected": ["payment-service", "order-service"],
        "expected_remediation": "restart_service",
        "severity": "HIGH",
    },
    "FAIL_NOTIFICATION": {
        "description": "Crash notification-service",
        "target": "notification-service",
        "flags": {"notification-service": {"crash": "1"}},
        "expected_root_cause": "notification service failure",
        "expected_affected": ["notification-service", "order-service"],
        "expected_remediation": "restart_service",
        "severity": "MEDIUM",
    },
    "FAIL_TRAFFIC_SPIKE": {
        "description": "Mark traffic-spike flag (load generator uses this)",
        "target": "gateway",
        "flags": {"gateway": {"traffic_spike": "1"}},
        "expected_root_cause": "traffic spike overload",
        "expected_affected": ["gateway", "order-service"],
        "expected_remediation": "scale_service",
        "severity": "MEDIUM",
    },
    "FAIL_CPU_STRESS": {
        "description": "CPU stress on payment-service",
        "target": "payment-service",
        "flags": {"payment-service": {"cpu_stress": "1"}},
        "expected_root_cause": "payment service injected or handler latency",
        "expected_affected": ["payment-service"],
        "expected_remediation": "restart_service",
        "severity": "MEDIUM",
    },
    "FAIL_MEMORY_STRESS": {
        "description": "Memory stress on payment-service",
        "target": "payment-service",
        "flags": {"payment-service": {"mem_stress": "1", "mem_mb": "48"}},
        "expected_root_cause": "payment service injected or handler latency",
        "expected_affected": ["payment-service"],
        "expected_remediation": "restart_service",
        "severity": "MEDIUM",
    },
}


async def _client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


async def start_scenario(name: str) -> dict:
    if name not in SCENARIOS:
        raise ValueError("unknown scenario")
    spec = SCENARIOS[name]
    r = await _client()
    await r.sadd("failure_active_set", name)
    await r.hset(
        f"failure_active:{name}",
        mapping={"started_at": datetime.now(timezone.utc).isoformat(), "target": spec["target"]},
    )
    # Store each scenario independently; service flags are rebuilt so stopping
    # one scenario cannot erase another scenario affecting the same service.
    for svc, flags in spec["flags"].items():
        await r.hset(f"failure_scenario:{name}:{svc}", mapping=flags)
        await _rebuild_service_flags(r, svc)
    await r.aclose()
    return {"scenario": name, "status": "started", **spec}


async def stop_scenario(name: str) -> dict:
    if name not in SCENARIOS:
        raise ValueError("unknown scenario")
    spec = SCENARIOS[name]
    r = await _client()
    await r.srem("failure_active_set", name)
    await r.delete(f"failure_active:{name}")
    for svc in spec["flags"]:
        await r.delete(f"failure_scenario:{name}:{svc}")
        await _rebuild_service_flags(r, svc)
    await r.aclose()
    return {"scenario": name, "status": "stopped"}


async def stop_all_for_target(target: str) -> None:
    r = await _client()
    active = await r.smembers("failure_active_set")
    for name in active:
        spec = SCENARIOS.get(name)
        if spec and target in spec["flags"]:
            await r.delete(f"failure_scenario:{name}:{target}")
            await r.delete(f"failure_active:{name}")
            await r.srem("failure_active_set", name)
    await _rebuild_service_flags(r, target)
    await r.aclose()


async def _rebuild_service_flags(r: redis.Redis, service: str) -> None:
    """Merge active scenario flags for a service into the legacy service key."""
    merged: dict[str, str] = {}
    for name in await r.smembers("failure_active_set"):
        merged.update(await r.hgetall(f"failure_scenario:{name}:{service}"))
    key = f"failure:{service}"
    await r.delete(key)
    if merged:
        await r.hset(key, mapping=merged)


async def list_active() -> list[dict]:
    r = await _client()
    names = await r.smembers("failure_active_set")
    out = []
    for name in names:
        meta = await r.hgetall(f"failure_active:{name}")
        spec = SCENARIOS.get(name, {})
        out.append({"scenario": name, **spec, **meta})
    await r.aclose()
    return out
