"""Real-stack E2E. It deliberately skips when Docker/services are not running."""
import os
import time
import unittest
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE = os.getenv("APIR_E2E_BASE_URL", "http://localhost:8000")
GATEWAY = os.getenv("APIR_E2E_GATEWAY_URL", "http://localhost:8080")

def request(path, token=None, method="GET", body=None, timeout=45):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    return urlopen(Request(BASE + path, data=body, headers=headers, method=method), timeout=timeout)

class PaymentLatencyE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try: request("/health")
        except URLError: raise unittest.SkipTest("BLOCKED BY ENVIRONMENT: Docker APIR stack is not reachable")
        import json
        raw = request("/auth/login", method="POST", body=json.dumps({"username":"sre","password":"sre123"}).encode()).read()
        cls.token = json.loads(raw)["access_token"]
    def test_payment_latency_to_resolved(self):
        import json
        # Clear any existing payment-service incidents first
        try:
            existing = json.loads(request("/incidents", self.token).read())
            for inc in existing:
                if inc.get("service") == "payment-service" and inc.get("status") not in {"RESOLVED", "FAILED"}:
                    try:
                        request(f'/incidents/{inc["incident_id"]}', self.token, "PATCH", json.dumps({"status": "RESOLVED"}).encode())
                        print(f"Resolved existing incident {inc['incident_id']}")
                    except:
                        pass
        except Exception as e:
            print(f"Error clearing existing incidents: {e}")
        
        failure_start = time.time()
        print(f"Failure start timestamp: {failure_start:.2f}")
        request("/failures/FAIL_PAYMENT_LATENCY/start", self.token, "POST", b"{}")
        try:
            # Generate real order traffic through the gateway so Prometheus sees the injected delay.
            for i in range(12):
                t_req = time.time()
                try:
                    resp = urlopen(Request(GATEWAY + "/orders", data=json.dumps({"user_id":"user123", "items":[{"product_id":"P001", "quantity":1}], "payment_method":"card"}).encode(), headers={"Content-Type":"application/json"}, method="POST"), timeout=15)
                    lat = (time.time() - t_req) * 1000
                    print(f"Traffic request {i} completed: status={resp.status}, latency={lat:.1f}ms")
                except URLError as e:
                    lat = (time.time() - t_req) * 1000
                    print(f"Traffic request {i} failed after {lat:.1f}ms: {e}")
                    pass
            print(f"Traffic generation completed at {time.time() - failure_start:.1f}s after failure start")
            
            # Check Prometheus metrics directly
            try:
                prom_response = urlopen(Request("http://localhost:9090/api/v1/query?query=histogram_quantile(0.95%2C%20sum%20by%20(le)%20(rate(request_latency_seconds_bucket%7Bservice%3D%22payment-service%22%7D%5B1m%5D)))%20*%201000"), timeout=5)
                prom_data = json.loads(prom_response.read())
                print(f"Prometheus payment-service p95 latency query result: {prom_data.get('data', {}).get('result')}")
            except Exception as e:
                print(f"Failed to query Prometheus: {e}")
            
            deadline=time.time()+90; incident=None
            check_count = 0
            while time.time()<deadline:
                check_count += 1
                try:
                    prom_response = urlopen(Request("http://localhost:9090/api/v1/query?query=histogram_quantile(0.95%2C%20sum%20by%20(le)%20(rate(request_latency_seconds_bucket%7Bservice%3D%22payment-service%22%7D%5B1m%5D)))%20*%201000"), timeout=5)
                    prom_data = json.loads(prom_response.read())
                    print(f"Check {check_count} Prometheus payment-service p95: {prom_data.get('data', {}).get('result')}")
                except Exception:
                    pass
                rows=json.loads(request("/incidents", self.token).read())
                print(f"Check {check_count} at {time.time() - failure_start:.1f}s: {len(rows)} total incidents")
                for row in rows:
                    print(f"  - {row.get('incident_id')[:8]}: service={row.get('service')}, status={row.get('status')}, type={row.get('incident_type')}")
                incident=next((x for x in rows if x["service"]=="payment-service" and x["status"] not in {"RESOLVED","FAILED"}),None)
                if incident:
                    print(f"Found incident: {incident}")
                    break
                time.sleep(3)
            print(f"Checked {check_count} times over {time.time() - failure_start:.1f}s")
            self.assertIsNotNone(incident, "detector did not create a payment incident")
            detail=json.loads(request(f'/incidents/{incident["incident_id"]}/investigate',self.token,"POST",b"{}").read())
            self.assertTrue(detail["investigation"]["rca"]["hypotheses"])
            plan=detail["remediation"]["plan_id"]
            request(f"/remediation/{plan}/approve",self.token,"POST",json.dumps({"reason":"E2E approval"}).encode())
            final=json.loads(request(f'/incidents/{incident["incident_id"]}',self.token).read())
            self.assertEqual(final["incident"]["status"],"RESOLVED")
        finally: request("/failures/FAIL_PAYMENT_LATENCY/stop",self.token,"POST",b"{}")

if __name__ == "__main__": unittest.main()
