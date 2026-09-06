from __future__ import annotations

from typing import Any
from app.action_registry import ALLOWED_ACTIONS, ALLOWED_TARGETS
from app.config import settings


def evaluate_remediation_policy(
    action_id: str,
    target: str,
    confidence: float,
    severity: str,
    blast_info: dict[str, Any],
    historical_success_rate: float | None = None,
    rollback_available: bool = True,
    auto_execute_low_risk: bool | None = None,
) -> dict[str, Any]:
    """
    Deterministic risk-aware remediation policy engine.
    Outputs: AUTO_EXECUTE | REQUIRE_APPROVAL | REJECT.
    """
    if auto_execute_low_risk is None:
        auto_execute_low_risk = settings.auto_execute_low_risk
    # 1. Allowlist safety gate
    if action_id not in ALLOWED_ACTIONS:
        return {
            "decision": "REJECT",
            "action": action_id,
            "target": target,
            "confidence": confidence,
            "risk": "UNKNOWN",
            "reason": f"Action '{action_id}' is not in the allowlisted action registry.",
            "policy_inputs": {"allowed_action": False},
        }

    spec = ALLOWED_ACTIONS[action_id]
    action_risk = spec["risk_level"]  # LOW, MEDIUM, HIGH

    if target not in ALLOWED_TARGETS:
        return {
            "decision": "REJECT",
            "action": action_id,
            "target": target,
            "confidence": confidence,
            "risk": action_risk,
            "reason": f"Target '{target}' is not an authorized remediation target.",
            "policy_inputs": {"allowed_target": False},
        }

    blast_count = blast_info.get("affected_count", 1)
    blast_level = blast_info.get("blast_radius_level", "LOW")

    policy_inputs = {
        "action_id": action_id,
        "target": target,
        "confidence": confidence,
        "severity": severity,
        "action_risk": action_risk,
        "blast_radius_count": blast_count,
        "blast_radius_level": blast_level,
        "rollback_available": rollback_available,
        "historical_success_rate": historical_success_rate,
        "auto_execute_low_risk": settings.auto_execute_low_risk,
        "dry_run_mode": settings.dry_run_mode,
    }

    # 2. Critical or High risk actions ALWAYS require approval
    if action_risk == "HIGH":
        return {
            "decision": "REQUIRE_APPROVAL",
            "action": action_id,
            "target": target,
            "confidence": confidence,
            "risk": action_risk,
            "reason": f"Action '{action_id}' has HIGH risk level; operator approval is strictly required.",
            "policy_inputs": policy_inputs,
        }

    # 3. Large blast radius (> 3 services) requires approval
    if blast_count > 3 or blast_level == "HIGH":
        return {
            "decision": "REQUIRE_APPROVAL",
            "action": action_id,
            "target": target,
            "confidence": confidence,
            "risk": action_risk,
            "reason": f"Blast radius is HIGH ({blast_count} services impacted); operator sign-off required.",
            "policy_inputs": policy_inputs,
        }

    # 4. Low confidence (< 0.70) requires approval
    if confidence < 0.70:
        return {
            "decision": "REQUIRE_APPROVAL",
            "action": action_id,
            "target": target,
            "confidence": confidence,
            "risk": action_risk,
            "reason": f"RCA confidence ({confidence:.2f}) is below the automated threshold (0.70); manual review required.",
            "policy_inputs": policy_inputs,
        }

    # 5. Historical degradation guard: if historically failed >= 50% of the time, require approval
    if historical_success_rate is not None and historical_success_rate < 0.50:
        return {
            "decision": "REQUIRE_APPROVAL",
            "action": action_id,
            "target": target,
            "confidence": confidence,
            "risk": action_risk,
            "reason": f"Historical success rate ({historical_success_rate * 100:.1f}%) is poor; operator sign-off required.",
            "policy_inputs": policy_inputs,
        }

    # 6. Auto-execute eligible:
    # If auto_execute_low_risk is enabled AND risk is LOW AND confidence >= 0.85 AND blast <= 3 AND rollback available
    if auto_execute_low_risk and action_risk == "LOW" and confidence >= 0.85 and rollback_available:
        return {
            "decision": "AUTO_EXECUTE",
            "action": action_id,
            "target": target,
            "confidence": confidence,
            "risk": action_risk,
            "reason": (
                f"Automated execution approved: high confidence ({confidence:.2f}), LOW risk, "
                f"blast radius {blast_count} service(s), rollback available."
            ),
            "policy_inputs": policy_inputs,
        }

    # Default safe behavior: require approval
    return {
        "decision": "REQUIRE_APPROVAL",
        "action": action_id,
        "target": target,
        "confidence": confidence,
        "risk": action_risk,
        "reason": (
            f"Remediation policy requires approval for {action_id} on {target} "
            f"(risk: {action_risk}, confidence: {confidence:.2f}, blast: {blast_count})."
        ),
        "policy_inputs": policy_inputs,
    }
