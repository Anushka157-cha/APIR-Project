from __future__ import annotations

from typing import Any
from app.dependency_graph import upstream, downstream, SERVICES


def calculate_blast_radius(target: str, action: str = "restart_service") -> dict[str, Any]:
    """
    Calculate the potential operational blast radius before executing a remediation action.
    Uses the real architecture dependency graph.
    """
    clean_target = target.strip()
    if clean_target not in SERVICES and f"{clean_target}-service" in SERVICES:
        clean_target = f"{clean_target}-service"
    elif clean_target.endswith("-service") and clean_target.replace("-service", "") in SERVICES:
        clean_target = clean_target.replace("-service", "")

    # Direct target
    affected = [clean_target]

    # Services depending on this target (callers who may fail if it is restarted/down)
    callers = upstream(clean_target)
    for c in callers:
        if c not in affected:
            affected.append(c)

    # If action is disruptive (e.g. rollback or network change), downstream callees may also be touched
    if action in {"rollback_service", "scale_service"}:
        callees = downstream(clean_target)
        for d in callees:
            if d not in affected:
                affected.append(d)

    count = len(affected)
    if count <= 1:
        level = "LOW"
    elif count <= 3:
        level = "MEDIUM"
    else:
        level = "HIGH"

    # Dependency depth from gateway
    depth = 0
    if clean_target == "gateway":
        depth = 0
    elif clean_target == "order-service":
        depth = 1
    else:
        depth = 2

    return {
        "target": clean_target,
        "action": action,
        "blast_radius_level": level,
        "affected_count": count,
        "affected_services": affected,
        "dependency_depth": depth,
        "description": f"Remediating {clean_target} potentially impacts {count} service(s): {', '.join(affected)}.",
    }
