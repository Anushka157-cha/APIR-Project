from __future__ import annotations

from typing import Set

# Canonical Incident Lifecycle States
class IncidentState:
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    MITIGATING = "MITIGATING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"

VALID_INCIDENT_STATES: Set[str] = {
    IncidentState.OPEN,
    IncidentState.INVESTIGATING,
    IncidentState.MITIGATING,
    IncidentState.VERIFYING,
    IncidentState.RESOLVED,
    IncidentState.FAILED,
    IncidentState.ROLLING_BACK,
    IncidentState.ROLLED_BACK,
}

# Permitted state transitions
ALLOWED_TRANSITIONS: dict[str, Set[str]] = {
    "OPEN": {"INVESTIGATING", "MITIGATING", "RESOLVED", "FAILED"},
    "INVESTIGATING": {"MITIGATING", "VERIFYING", "RESOLVED", "FAILED"},
    "MITIGATING": {"VERIFYING", "ROLLING_BACK", "RESOLVED", "FAILED"},
    "VERIFYING": {"RESOLVED", "ROLLING_BACK", "FAILED", "PARTIALLY_RESOLVED"},
    "ROLLING_BACK": {"ROLLED_BACK", "RESOLVED", "FAILED"},
    "ROLLED_BACK": {"RESOLVED", "FAILED", "INVESTIGATING"},
    "PARTIALLY_RESOLVED": {"RESOLVED", "FAILED", "INVESTIGATING"},
    "FAILED": {"ROLLING_BACK", "INVESTIGATING", "RESOLVED"},
    "RESOLVED": {"OPEN"},  # Re-opening if re-occurred
}


def can_transition(current_state: str, target_state: str) -> bool:
    """Check if state transition is legally permissible."""
    curr = current_state.upper()
    tgt = target_state.upper()

    # Idempotent re-affirmation is always allowed
    if curr == tgt:
        return True

    allowed = ALLOWED_TRANSITIONS.get(curr, set())
    return tgt in allowed


def transition_incident(current_state: str, target_state: str) -> str:
    """
    Validate and return target state, raising ValueError if the transition is illegal.
    """
    if not can_transition(current_state, target_state):
        raise ValueError(
            f"Invalid incident lifecycle transition: '{current_state}' -> '{target_state}'. "
            f"Permitted next states from '{current_state}': {sorted(list(ALLOWED_TRANSITIONS.get(current_state.upper(), set())))}"
        )
    return target_state.upper()
