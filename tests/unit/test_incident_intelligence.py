from __future__ import annotations

import sys
import unittest
sys.path.insert(0, "backend")

from app.incident_intelligence import (
    calculate_anomaly_score,
    compute_incident_fingerprint,
    build_intelligence_record,
)


class TestIncidentIntelligence(unittest.TestCase):
    def test_fingerprint_deterministic(self):
        fp1 = compute_incident_fingerprint("payment-service", "latency_spike", "p95_ms")
        fp2 = compute_incident_fingerprint("payment-service", "latency_spike", "p95_ms")
        self.assertEqual(fp1, fp2)
        self.assertEqual(fp1, "payment-service:latency_spike:p95_ms")

    def test_anomaly_score_normal_traffic(self):
        metrics = {"p95_ms": 80.0, "error_rate": 0.0, "health": 1.0, "rps": 10.0}
        baseline = {"p95_ms": [75.0, 80.0, 78.0], "error_rate": [0.0, 0.0]}
        res = calculate_anomaly_score(metrics, baseline, [])
        score = res["anomaly_score"]
        contributors = res["contributors"]
        self.assertGreaterEqual(score, 0.0)
        self.assertLess(score, 0.35)
        self.assertIn("p95_latency", contributors)
        self.assertIn("error_rate", contributors)

    def test_anomaly_score_severe_outage(self):
        metrics = {"p95_ms": 2500.0, "error_rate": 0.45, "health": 0.0, "rps": 5.0}
        baseline = {"p95_ms": [100.0, 105.0, 95.0], "error_rate": [0.01, 0.0]}
        res = calculate_anomaly_score(metrics, baseline, ["latency_threshold", "service_crash"])
        score = res["anomaly_score"]
        contributors = res["contributors"]
        self.assertGreaterEqual(score, 0.7)
        self.assertLessEqual(score, 1.0)
        self.assertGreater(contributors["p95_latency"], 0.0)
        self.assertGreater(contributors["error_rate"], 0.0)
        self.assertGreater(contributors["service_health"], 0.0)

    def test_build_intelligence_record(self):
        metrics = {"p95_ms": 1200.0, "error_rate": 0.15, "health": 1.0, "rps": 8.0}
        baseline = {"p95_ms": [100.0, 110.0, 90.0], "error_rate": [0.0]}
        record = build_intelligence_record(
            service="order-service",
            incident_type="high_latency",
            metrics=metrics,
            findings=["latency_threshold"],
            baseline=baseline,
        )
        self.assertEqual(record["affected_service"], "order-service")
        self.assertEqual(record["incident_type"], "high_latency")
        self.assertIn("anomaly_score", record)
        self.assertIn("contributors", record)
        self.assertIn("observed_value", record)
        self.assertIn("baseline_value", record)
        self.assertIn("explanation", record)
        self.assertEqual(record["fingerprint"], "order-service:high_latency:p95_ms")


if __name__ == "__main__":
    unittest.main()
