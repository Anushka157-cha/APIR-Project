from __future__ import annotations

from typing import Any
from app.dependency_graph import upstream, downstream, SERVICES


def evaluate_causal_propagation(
    origin_service: str,
    snapshot: dict[str, dict[str, float]],
    metric_signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Deterministically analyze the dependency topology to distinguish
    the probable ROOT CAUSE from cascading DOWNSTREAM VICTIMS.
    """
    metric_signals = metric_signals or []
    degraded_services: list[str] = []

    for svc in SERVICES:
        m = snapshot.get(svc) or {}
        p95 = m.get("p95_ms") or 0.0
        err = m.get("error_rate") or 0.0
        health = m.get("health")
        if health is None:
            health = 1.0
        if health < 1.0 or p95 >= 800.0 or err >= 0.05:
            degraded_services.append(svc)

    # In call graph: gateway -> order-service -> (payment, inventory, notification)
    # If a callee is degraded (e.g. payment-service), its callers (order, gateway)
    # will naturally show elevated latency as downstream victims of the call.
    service_roles: dict[str, dict[str, Any]] = {}
    downstream_victims: list[str] = []
    root_candidates: list[str] = []

    for svc in degraded_services:
        callers = upstream(svc)
        callees = downstream(svc)
        
        # Check if any callee of this service is also degraded
        callees_degraded = [c for c in callees if c in degraded_services]
        
        if callees_degraded:
            # This service is an upstream caller of a degraded dependency;
            # therefore it is a victim of cascading failure/latency.
            deepest_cause = callees_degraded[-1]
            service_roles[svc] = {
                "role": "DOWNSTREAM_VICTIM",
                "explanation": f"{svc} is a downstream victim of {deepest_cause} (callee failure propagated to caller).",
                "caused_by": deepest_cause,
            }
            downstream_victims.append(svc)
        else:
            # No degraded callees; this service is the origin of the anomaly
            service_roles[svc] = {
                "role": "ROOT_CAUSE_ORIGIN",
                "explanation": f"{svc} is the origin dependency with acute anomaly and no degraded dependencies.",
                "caused_by": None,
            }
            root_candidates.append(svc)

    # If origin_service was detected, ensure it is ranked primary if it has no degraded callees
    primary_root = origin_service
    if root_candidates:
        # Prefer the origin if it's in candidates, else the first candidate
        primary_root = origin_service if origin_service in root_candidates else root_candidates[0]

    # Explain causality
    if downstream_victims and primary_root in degraded_services:
        causal_narrative = (
            f"{primary_root} is identified as the primary root cause because it is the deepest dependency "
            f"showing acute degradation. {', '.join(downstream_victims)} exhibited correlated latency/error "
            f"propagation as downstream victims in the call chain."
        )
    elif primary_root in degraded_services:
        causal_narrative = f"{primary_root} exhibited isolated anomaly with no cascade detected."
    else:
        causal_narrative = f"Monitoring {primary_root}; no cascading propagation observed."

    return {
        "primary_root_cause": primary_root,
        "degraded_services": degraded_services,
        "downstream_victims": downstream_victims,
        "root_candidates": root_candidates,
        "service_roles": service_roles,
        "causal_narrative": causal_narrative,
    }


def calibrate_confidence(
    hypothesis_name: str,
    origin_service: str,
    metric_signals: list[dict[str, Any]],
    log_signals: list[dict[str, Any]],
    rag_hits: list[dict[str, Any]],
    causal_info: dict[str, Any],
) -> dict[str, Any]:
    """
    Calculate deterministic, explainable confidence breakdown.
    """
    # 1. Metric evidence (0.0 to 0.35)
    metric_score = 0.0
    for m in metric_signals:
        svc = m.get("service") or ""
        change = abs(m.get("change_percent") or 0.0)
        if origin_service in svc and change >= 40.0:
            metric_score = min(0.35, metric_score + (change / 500.0) * 0.25)
    metric_score = round(max(0.10, min(0.35, metric_score)), 3)

    # 2. Dependency / Causal evidence (0.0 to 0.25)
    if causal_info.get("primary_root_cause") == origin_service:
        dep_score = 0.25
    elif origin_service in causal_info.get("root_candidates", []):
        dep_score = 0.20
    else:
        dep_score = 0.10

    # 3. Temporal consistency (0.0 to 0.20)
    # Origin anomaly precedes or coincides with symptoms
    temporal_score = 0.20 if origin_service == causal_info.get("primary_root_cause") else 0.12

    # 4. RAG / Runbook correlation (0.0 to 0.15)
    rag_score = 0.0
    for r in rag_hits:
        score = float(r.get("relevance_score") or 0.0)
        if any(w in r.get("document", "").lower() for w in hypothesis_name.lower().split()[:2]):
            rag_score = max(rag_score, min(0.15, score * 0.3))
    rag_score = round(rag_score, 3)

    # 5. Log evidence (0.0 to 0.10)
    log_score = 0.05 if log_signals else 0.0

    # 6. Contradiction penalty (-0.05 to -0.15)
    penalty = 0.0
    if origin_service in causal_info.get("downstream_victims", []):
        penalty = -0.12  # Penalize calling an obvious victim the root cause

    total = metric_score + dep_score + temporal_score + rag_score + log_score + penalty
    final_confidence = round(max(0.20, min(0.98, total)), 2)

    return {
        "confidence": final_confidence,
        "breakdown": {
            "metric_evidence": metric_score,
            "dependency_causal_evidence": dep_score,
            "temporal_precedence": temporal_score,
            "runbook_correlation": rag_score,
            "log_evidence": log_score,
            "contradiction_penalty": penalty,
        },
        "formula": "metric + dependency + temporal + runbook + logs + penalty",
    }
