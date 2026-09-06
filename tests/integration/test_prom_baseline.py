import asyncio
import sys
import unittest
sys.path.insert(0, "backend")
from app.prom import PrometheusClient

class StubPrometheus(PrometheusClient):
    async def query_range(self, expression, **kwargs):
        return [{"values": [[1, "1.0"], [2, "2.5"], [3, "bad"]]}]

class PrometheusBaselineIntegrationTests(unittest.TestCase):
    def test_range_baseline_uses_prometheus_values(self):
        baseline = asyncio.run(StubPrometheus("http://unused").baseline("payment-service", minutes=5))
        self.assertEqual(baseline["payment-service:p95_ms"], [1.0, 2.5])
        self.assertEqual(baseline["payment-service:error_rate"], [1.0, 2.5])

if __name__ == "__main__": unittest.main()
