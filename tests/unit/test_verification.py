import asyncio
import sys
import unittest
sys.path.insert(0, "backend")
from app.verification import verify_recovery, verify_stabilized

class Prom:
    def __init__(self, snapshots): self.snapshots = iter(snapshots)
    async def snapshot(self): return next(self.snapshots)

class VerificationTests(unittest.TestCase):
    def test_failed_when_unhealthy(self):
        result = verify_recovery({"payment-service": {"p95_ms": 2000, "error_rate": .5}}, {"payment-service": {"p95_ms": 2000, "error_rate": .5, "health": 0}}, "payment-service")
        self.assertEqual(result["status"], "FAILED")
    def test_requires_all_stable_samples(self):
        before = {"payment-service": {"p95_ms": 2000, "error_rate": .5}}
        healthy = {"payment-service": {"p95_ms": 20, "error_rate": 0, "health": 1}}
        result = asyncio.run(verify_stabilized(before, "payment-service", prom=Prom([healthy, healthy, healthy]), samples=3, interval=0))
        self.assertEqual(result["status"], "RESOLVED"); self.assertEqual(result["samples_used"], 3)

if __name__ == "__main__": unittest.main()
