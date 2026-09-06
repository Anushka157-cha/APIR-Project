from __future__ import annotations

import sys
import unittest
sys.path.insert(0, "backend")

from app.blast_radius import calculate_blast_radius
from app.remediation_policy import evaluate_remediation_policy


class TestRemediationPolicy(unittest.TestCase):
    def test_blast_radius_payment_service(self):
        br = calculate_blast_radius("payment-service", "restart_service")
        self.assertEqual(br["target"], "payment-service")
        self.assertIn("order-service", br["affected_services"])
        self.assertIn("gateway", br["affected_services"])
        self.assertGreaterEqual(br["affected_count"], 2)
        self.assertIn(br["blast_radius_level"], {"LOW", "MEDIUM", "HIGH"})

    def test_policy_auto_execute_low_risk_high_confidence(self):
        blast_info = {"affected_count": 1, "blast_radius_level": "LOW"}
        res = evaluate_remediation_policy(
            action_id="restart_service",
            target="payment-service",
            confidence=0.92,
            severity="MEDIUM",
            blast_info=blast_info,
            historical_success_rate=1.0,
            rollback_available=True,
            auto_execute_low_risk=True,
        )
        self.assertEqual(res["decision"], "AUTO_EXECUTE")
        self.assertFalse(res.get("needs_approval", False))

    def test_policy_require_approval_critical_action(self):
        # Even with high confidence, if action has high blast radius or is dangerous:
        blast_info = {"affected_count": 5, "blast_radius_level": "HIGH"}
        res = evaluate_remediation_policy(
            action_id="restart_service",
            target="payment-service",
            confidence=0.95,
            severity="CRITICAL",
            blast_info=blast_info,
            historical_success_rate=0.5,
            rollback_available=True,
        )
        self.assertEqual(res["decision"], "REQUIRE_APPROVAL")
        self.assertTrue(res.get("needs_approval", True))

    def test_policy_require_approval_low_confidence(self):
        blast_info = {"affected_count": 1, "blast_radius_level": "LOW"}
        res = evaluate_remediation_policy(
            action_id="restart_service",
            target="payment-service",
            confidence=0.60,
            severity="MEDIUM",
            blast_info=blast_info,
            historical_success_rate=1.0,
            rollback_available=True,
        )
        self.assertEqual(res["decision"], "REQUIRE_APPROVAL")
        self.assertTrue(res.get("needs_approval", True))

    def test_policy_reject_unknown_action(self):
        blast_info = {"affected_count": 1, "blast_radius_level": "LOW"}
        res = evaluate_remediation_policy(
            action_id="rm_rf_root",
            target="payment-service",
            confidence=0.95,
            severity="CRITICAL",
            blast_info=blast_info,
            historical_success_rate=1.0,
            rollback_available=True,
        )
        self.assertEqual(res["decision"], "REJECT")
        self.assertIn("not in the allowlisted", res["reason"])


if __name__ == "__main__":
    unittest.main()
