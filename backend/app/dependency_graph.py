from __future__ import annotations

from dataclasses import dataclass, field


SERVICES = [
    "gateway",
    "order-service",
    "inventory-service",
    "payment-service",
    "notification-service",
]

# Directed edge: caller -> callee
EDGES: list[tuple[str, str]] = [
    ("gateway", "order-service"),
    ("order-service", "inventory-service"),
    ("order-service", "payment-service"),
    ("order-service", "notification-service"),
]


@dataclass
class GraphNode:
    id: str
    label: str
    health: str = "unknown"
    data: dict = field(default_factory=dict)


def downstream(service: str) -> list[str]:
    seen: list[str] = []
    stack = [service]
    visited = {service}
    while stack:
        node = stack.pop()
        for src, dst in EDGES:
            if src == node and dst not in visited:
                visited.add(dst)
                seen.append(dst)
                stack.append(dst)
    return seen


def upstream(service: str) -> list[str]:
    seen: list[str] = []
    stack = [service]
    visited = {service}
    while stack:
        node = stack.pop()
        for src, dst in EDGES:
            if dst == node and src not in visited:
                visited.add(src)
                seen.append(src)
                stack.append(src)
    return seen


def affected_from(service: str) -> list[str]:
    """Callers that fail when this service fails, plus the service itself."""
    return [service] + upstream(service)


def impact_rank(service: str) -> list[dict]:
    ranked = []
    for name in [service] + upstream(service) + downstream(service):
        if any(r["service"] == name for r in ranked):
            continue
        score = 1.0 if name == service else 0.7 if name in upstream(service) else 0.4
        ranked.append({"service": name, "score": score, "role": _role(name, service)})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked


def _role(name: str, origin: str) -> str:
    if name == origin:
        return "origin"
    if name in upstream(origin):
        return "upstream_affected"
    return "downstream_dependency"


def react_flow(health: dict[str, str] | None = None) -> dict:
    health = health or {}
    positions = {
        "gateway": {"x": 280, "y": 0},
        "order-service": {"x": 280, "y": 140},
        "inventory-service": {"x": 40, "y": 300},
        "payment-service": {"x": 280, "y": 300},
        "notification-service": {"x": 520, "y": 300},
    }
    nodes = []
    for svc in SERVICES:
        nodes.append(
            {
                "id": svc,
                "position": positions[svc],
                "data": {
                    "label": svc,
                    "health": health.get(svc, "unknown"),
                },
                "type": "serviceNode",
            }
        )
    edges = [
        {
            "id": f"{a}->{b}",
            "source": a,
            "target": b,
            "animated": health.get(b) in {"unhealthy", "degraded"},
        }
        for a, b in EDGES
    ]
    return {"nodes": nodes, "edges": edges}
