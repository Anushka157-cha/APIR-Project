from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependency_graph import impact_rank, react_flow, upstream, downstream
from app.llm import get_llm
from app.prom import PrometheusClient
from app.rag import search
from app.scoring import rank_hypotheses, score_hypothesis

HYPOTHESIS_CATALOG = [
    "payment service injected or handler latency",
    "database connection pool exhaustion",
    "database unavailable",
    "inventory service crash",
    "network latency between services",
    "high injected error rate",
    "notification service failure",
    "traffic spike overload",
    "recent payment deployment regression",
]


async def collect_logs(r: redis.Redis, service: str | None = None) -> list[dict]:
    try:
        keys = [f"logs:{service}"] if service else []
        if not service:
            keys = [
                "logs:gateway",
                "logs:order-service",
                "logs:inventory-service",
                "logs:payment-service",
                "logs:notification-service",
            ]
        out = []
        for key in keys:
            raw = await r.lrange(key, 0, 200)
            for item in raw:
                try:
                    out.append(json.loads(item))
                except json.JSONDecodeError:
                    continue
        return out
    except Exception:
        return []


def analyze_logs(logs: list[dict]) -> list[dict]:
    patterns: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for log in logs:
        if (log.get("level") or "").upper() in {"ERROR", "WARNING"} or (log.get("status_code") or 0) >= 500:
            msg = (log.get("message") or "error")[:120]
            patterns[(log.get("service") or "unknown", msg)].append(log)
    results = []
    for (service, pattern), entries in sorted(patterns.items(), key=lambda item: len(item[1]), reverse=True)[:8]:
        times = [e.get("timestamp") for e in entries if e.get("timestamp")]
        levels = [str(e.get("level", "")).upper() for e in entries]
        results.append(
            {
                "service": service,
                "pattern": pattern,
                "frequency": len(entries),
                "first_seen": min(times) if times else None,
                "last_seen": max(times) if times else None,
                "request_ids": list(dict.fromkeys(e.get("request_id") for e in entries if e.get("request_id")))[:10],
                "trace_ids": list(dict.fromkeys(e.get("trace_id") for e in entries if e.get("trace_id")))[:10],
                "severity": "ERROR" if "ERROR" in levels or any((e.get("status_code") or 0) >= 500 for e in entries) else "WARNING",
            }
        )
    return results


def analyze_metrics(snap: dict, service: str, history: dict[str, list[float]] | None = None) -> list[dict]:
    """Compare observations to supplied collection history; never invent baselines."""
    history = history or {}
    findings = []
    for svc, metrics in snap.items():
        for metric_name in ("p95_ms", "error_rate", "rps"):
            current = metrics.get(metric_name) or 0
            samples = history.get(f"{svc}:{metric_name}", [])
            if len(samples) < 2:
                continue
            baseline = sum(samples) / len(samples)
            variance = sum((v - baseline) ** 2 for v in samples) / len(samples)
            stddev = variance ** 0.5
            median = sorted(samples)[len(samples) // 2]
            change = ((current - baseline) / baseline) * 100 if baseline else (100.0 if current else 0.0)
            if abs(change) < 80 and svc != service:
                continue
            if abs(change) < 40:
                continue
            z_score = 0.0
            if stddev and stddev > 0:
                try:
                    z_score = (current - baseline) / stddev
                    if not (z_score >= -1e308 and z_score <= 1e308):  # Check for inf/nan
                        z_score = 0.0
                except (ZeroDivisionError, OverflowError):
                    z_score = 0.0
            findings.append(
                {
                    "metric": f"{svc}_{metric_name}",
                    "service": svc,
                    "baseline": baseline,
                    "median": median,
                    "stddev": round(stddev, 4) if stddev and stddev >= 0 else 0.0,
                    "current": round(current, 3),
                    "change_percent": round(change, 1),
                    "z_score": round(z_score, 3),
                    "anomaly": abs(change) >= 40,
                    "evidence": f"{metric_name} on {svc}",
                }
            )
    return findings


async def investigate(session: AsyncSession, incident: dict) -> dict:
    llm = get_llm()
    prom = PrometheusClient()
    service = incident["service"]
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1.5)
        logs = await collect_logs(r, None)
        await r.aclose()
    except Exception:
        logs = []
    # Incident evidence is constrained to the recent buffer around detection.
    detected = incident.get("detected_at")
    if detected:
        try:
            since = datetime.fromisoformat(str(detected).replace("Z", "+00:00")) - timedelta(minutes=5)
            logs = [l for l in logs if not l.get("timestamp") or datetime.fromisoformat(str(l["timestamp"]).replace("Z", "+00:00")) >= since]
        except (TypeError, ValueError):
            pass
    log_struct = analyze_logs(logs)
    snap = await prom.snapshot()
    metadata = incident.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    metric_history = metadata.get("metric_history", {})
    if not any(metric_history.values()):
        metric_history = await prom.baseline(service)
    metric_struct = analyze_metrics(snap, service, metric_history)
    dep = impact_rank(service)
    rag_hits = await search(
        session,
        f"{incident.get('incident_type')} {service} {incident.get('title')} {' '.join(p['pattern'] for p in log_struct[:3])}",
        limit=6,
    )
    
    from app.causal_rca import evaluate_causal_propagation, calibrate_confidence
    from app.blast_radius import calculate_blast_radius
    causal = evaluate_causal_propagation(service, snap, metric_struct)
    blast = calculate_blast_radius(service)

    # Untrusted retrieved text is passed only as data fields, never as system instructions.
    hypotheses = []
    mentioned = [service] + [d["service"] for d in dep]
    for name in HYPOTHESIS_CATALOG:
        base_h = score_hypothesis(
            name=name,
            metric_signals=metric_struct,
            log_signals=log_struct,
            rag_hits=rag_hits,
            origin_service=service,
            mentioned_services=mentioned,
        )
        calibrated = calibrate_confidence(name, service, metric_struct, log_struct, rag_hits, causal)
        base_h["confidence"] = max(base_h["confidence"], calibrated["confidence"])
        base_h["score_parts"].update(calibrated["breakdown"])
        hypotheses.append(base_h)

    ranked = rank_hypotheses(hypotheses)[:5]
    rca_payload = {
        "summary": f"{causal['causal_narrative']} Ranked {len(ranked)} hypotheses for {service} using metrics, logs, graph, and RAG.",
        "hypotheses": ranked,
        "causal_analysis": causal,
        "blast_radius": blast,
    }
    try:
        rca = await llm.complete_json({"hypotheses": ranked, "summary": rca_payload["summary"], "retrieved_data": rag_hits, "logs_data": log_struct, "metrics_data": metric_struct}, "rca")
        if not isinstance(rca, dict) or not isinstance(rca.get("hypotheses"), list):
            rca = rca_payload
        else:
            rca["causal_analysis"] = causal
            rca["blast_radius"] = blast
    except Exception:
        rca = rca_payload
    await r.aclose()
    return {
        "investigated_at": datetime.now(timezone.utc).isoformat(),
        "logs": log_struct,
        "metrics": metric_struct,
        "snapshot": snap,
        "graph": react_flow({k: ("healthy" if (v.get("health") or 1) >= 1 else "unhealthy") for k, v in snap.items()}),
        "impact": dep,
        "upstream": upstream(service),
        "downstream": downstream(service),
        "rag": rag_hits,
        "rca": rca,
        "causal": causal,
        "blast_radius": blast,
        "traces": [l for l in logs if l.get("trace_id")][:40],
    }


def propose_remediation(incident: dict, rca: dict) -> dict:
    from app.blast_radius import calculate_blast_radius
    from app.remediation_policy import evaluate_remediation_policy

    top = (rca.get("hypotheses") or [{}])[0]
    name = (top.get("hypothesis") or "").lower()
    target = incident["service"]
    action = "restart_service"
    risk = "LOW"
    confidence = float(top.get("confidence") or 0.85)
    severity = incident.get("severity", "HIGH")
    reason = f"Top hypothesis: {top.get('hypothesis')} (confidence {top.get('confidence')})"
    if "network" in name:
        action = "rollback_service"
        risk = "HIGH"
        reason = "Network-level issue: clear injected delay flags rather than restart only"
    if "traffic spike" in name:
        action = "scale_service"
        risk = "MEDIUM"
    if "deployment" in name:
        action = "rollback_service"
        risk = "HIGH"

    blast_info = calculate_blast_radius(target, action)
    policy = evaluate_remediation_policy(
        action_id=action,
        target=target,
        confidence=confidence,
        severity=severity,
        blast_info=blast_info,
        rollback_available=True,
    )

    return {
        "action": action,
        "target": target,
        "risk": risk,
        "reason": reason,
        "expected_effect": "Return latency and error rate toward baseline after the allowlisted action.",
        "rollback_plan": "Re-apply previous failure flags or reverse scale if health regresses.",
        "confidence": confidence,
        "blast_radius": blast_info,
        "policy": policy,
        "policy_decision": policy["decision"],
    }
