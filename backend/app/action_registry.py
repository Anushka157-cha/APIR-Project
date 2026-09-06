from __future__ import annotations

from typing import Callable

ALLOWED_ACTIONS: dict[str, dict] = {
    "restart_service": {
        "action_id": "restart_service",
        "name": "Restart service",
        "risk_level": "LOW",
        "required_permissions": ["ADMIN", "SRE"],
        "rollback_strategy": "service process comes back via orchestrator restart policy",
    },
    "scale_service": {
        "action_id": "scale_service",
        "name": "Scale service",
        "risk_level": "MEDIUM",
        "required_permissions": ["ADMIN", "SRE"],
        "rollback_strategy": "scale back to previous replica count",
    },
    "rollback_service": {
        "action_id": "rollback_service",
        "name": "Rollback service config/failures",
        "risk_level": "HIGH",
        "required_permissions": ["ADMIN"],
        "rollback_strategy": "re-apply previous configuration flags",
    },
    "enable_feature_flag": {
        "action_id": "enable_feature_flag",
        "name": "Enable feature flag",
        "risk_level": "MEDIUM",
        "required_permissions": ["ADMIN", "SRE"],
        "rollback_strategy": "disable the same flag",
    },
}

ALLOWED_TARGETS = {
    "gateway",
    "order-service",
    "inventory-service",
    "payment-service",
    "notification-service",
    "order",
    "inventory",
    "payment",
    "notification",
}


def validate_action(action_id: str, target: str) -> dict:
    if action_id not in ALLOWED_ACTIONS:
        raise ValueError("unknown action rejected")
    if target not in ALLOWED_TARGETS:
        raise ValueError("unknown target rejected")
    spec = ALLOWED_ACTIONS[action_id]
    return {**spec, "target": target}
