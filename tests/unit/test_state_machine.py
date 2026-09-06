from __future__ import annotations

import sys
import unittest
sys.path.insert(0, "backend")

from app.state_machine import can_transition, IncidentState


class TestStateMachine(unittest.TestCase):
    def test_valid_forward_transitions(self):
        self.assertTrue(can_transition(IncidentState.OPEN, IncidentState.INVESTIGATING))
        self.assertTrue(can_transition(IncidentState.INVESTIGATING, IncidentState.MITIGATING))
        self.assertTrue(can_transition(IncidentState.MITIGATING, IncidentState.VERIFYING))
        self.assertTrue(can_transition(IncidentState.VERIFYING, IncidentState.RESOLVED))

    def test_failure_and_rollback_transitions(self):
        self.assertTrue(can_transition(IncidentState.VERIFYING, IncidentState.FAILED))
        self.assertTrue(can_transition(IncidentState.FAILED, IncidentState.ROLLING_BACK))
        self.assertTrue(can_transition(IncidentState.ROLLING_BACK, IncidentState.ROLLED_BACK))

    def test_invalid_transitions(self):
        self.assertFalse(can_transition(IncidentState.RESOLVED, IncidentState.INVESTIGATING))
        self.assertFalse(can_transition(IncidentState.RESOLVED, IncidentState.MITIGATING))
        self.assertFalse(can_transition(IncidentState.OPEN, IncidentState.ROLLING_BACK))
        self.assertFalse(can_transition(IncidentState.OPEN, IncidentState.ROLLED_BACK))

    def test_idempotent_transitions(self):
        self.assertTrue(can_transition(IncidentState.RESOLVED, IncidentState.RESOLVED))
        self.assertTrue(can_transition(IncidentState.OPEN, IncidentState.OPEN))


if __name__ == "__main__":
    unittest.main()
