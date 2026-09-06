import sys
import unittest
sys.path.insert(0, "backend")

from app.scoring import score_hypothesis
from app.stats import ewma, moving_average, zscore


class StatsAndScoringTests(unittest.TestCase):
    def test_moving_average_ewma_and_zscore(self):
        self.assertEqual(moving_average([1, 2, 3, 4], 2), 3.5)
        self.assertAlmostEqual(ewma([10, 20], 0.5), 15)
        self.assertGreater(zscore(30, [10, 11, 12, 13]), 5)

    def test_stronger_evidence_has_higher_confidence(self):
        weak = score_hypothesis(name="payment latency", metric_signals=[], log_signals=[], rag_hits=[], origin_service="payment-service", mentioned_services=[])
        strong = score_hypothesis(name="payment latency", metric_signals=[{"service": "payment-service", "change_percent": 300}], log_signals=[{"service": "payment-service", "pattern": "payment latency timeout", "frequency": 50}], rag_hits=[{"document": "payment-latency.md", "relevance_score": .9}], origin_service="payment-service", mentioned_services=["payment-service"])
        self.assertGreater(strong["confidence"], weak["confidence"])
        self.assertLessEqual(strong["confidence"], 1)


if __name__ == "__main__": unittest.main()
