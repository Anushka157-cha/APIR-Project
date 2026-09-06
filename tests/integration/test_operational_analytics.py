from __future__ import annotations

import sys
import unittest
sys.path.insert(0, "backend")

from app.analytics import compute_service_health_scores


class TestOperationalAnalytics(unittest.TestCase):
    def test_health_score_all_healthy(self):
        snapshot = {
            "gateway": {"health": 1.0, "p95_ms": 45.0, "error_rate": 0.0},
            "order-service": {"health": 1.0, "p95_ms": 55.0, "error_rate": 0.0},
            "payment-service": {"health": 1.0, "p95_ms": 60.0, "error_rate": 0.0},
            "inventory-service": {"health": 1.0, "p95_ms": 30.0, "error_rate": 0.0},
            "notification-service": {"health": 1.0, "p95_ms": 25.0, "error_rate": 0.0},
        }
        res = compute_service_health_scores(snapshot)
        self.assertEqual(res["system_score"], 100)
        self.assertEqual(res["system_status"], "HEALTHY")
        self.assertEqual(res["services"]["payment-service"]["score"], 100)
        self.assertEqual(len(res["services"]["payment-service"]["deductions"]), 0)

    def test_health_score_degraded_service(self):
        snapshot = {
            "gateway": {"health": 1.0, "p95_ms": 2200.0, "error_rate": 0.02},
            "order-service": {"health": 1.0, "p95_ms": 2100.0, "error_rate": 0.02},
            "payment-service": {"health": 0.0, "p95_ms": 2500.0, "error_rate": 0.15},
            "inventory-service": {"health": 1.0, "p95_ms": 30.0, "error_rate": 0.0},
            "notification-service": {"health": 1.0, "p95_ms": 25.0, "error_rate": 0.0},
        }
        res = compute_service_health_scores(snapshot)
        self.assertLess(res["system_score"], 100)
        pay_score = res["services"]["payment-service"]
        self.assertLess(pay_score["score"], 50)
        self.assertIn("availability_down", pay_score["deductions"])
        self.assertIn("critical_latency", pay_score["deductions"])
        self.assertIn("high_error_rate", pay_score["deductions"])


if __name__ == "__main__":
    unittest.main()
