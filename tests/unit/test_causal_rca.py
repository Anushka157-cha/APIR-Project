from __future__ import annotations

import sys
import unittest
sys.path.insert(0, "backend")

from app.causal_rca import evaluate_causal_propagation, calibrate_confidence


class TestCausalRCA(unittest.TestCase):
    def test_downstream_victim_classification(self):
        # payment-service degrades, affecting gateway and order-service
        snapshot = {
            "payment-service": {"p95_ms": 2200.0, "health": 1.0, "error_rate": 0.0},
            "order-service": {"p95_ms": 2300.0, "health": 1.0, "error_rate": 0.05},
            "gateway": {"p95_ms": 2400.0, "health": 1.0, "error_rate": 0.05},
            "inventory-service": {"p95_ms": 50.0, "health": 1.0, "error_rate": 0.0},
            "notification-service": {"p95_ms": 30.0, "health": 1.0, "error_rate": 0.0},
        }
        res = evaluate_causal_propagation("payment-service", snapshot)
        self.assertEqual(res["primary_root_cause"], "payment-service")
        self.assertIn("order-service", res["downstream_victims"])
        self.assertIn("gateway", res["downstream_victims"])
        self.assertIn("payment-service is identified as the primary root cause", res["causal_narrative"])

    def test_calibrate_confidence_high_evidence(self):
        causal_info = {
            "primary_root_cause": "payment-service",
            "root_candidates": ["payment-service"],
            "downstream_victims": ["order-service", "gateway"],
        }
        metric_signals = [{"service": "payment-service", "change_percent": 350.0}]
        log_signals = [{"pattern": "pool wait timeout", "frequency": 12}]
        rag_hits = [{"document": "payment-latency.md", "relevance_score": 0.85}]

        res = calibrate_confidence(
            hypothesis_name="payment latency spike",
            origin_service="payment-service",
            metric_signals=metric_signals,
            log_signals=log_signals,
            rag_hits=rag_hits,
            causal_info=causal_info,
        )
        self.assertGreaterEqual(res["confidence"], 0.70)
        self.assertEqual(res["breakdown"]["contradiction_penalty"], 0.0)

    def test_calibrate_confidence_victim_penalized(self):
        causal_info = {
            "primary_root_cause": "payment-service",
            "root_candidates": ["payment-service"],
            "downstream_victims": ["gateway"],
        }
        metric_signals = [{"service": "gateway", "change_percent": 200.0}]

        # If we mistakenly try to blame gateway (which is a known downstream victim):
        res = calibrate_confidence(
            hypothesis_name="gateway latency spike",
            origin_service="gateway",
            metric_signals=metric_signals,
            log_signals=[],
            rag_hits=[],
            causal_info=causal_info,
        )
        self.assertLess(res["breakdown"]["contradiction_penalty"], 0.0)


if __name__ == "__main__":
    unittest.main()
