"""Service crash / process unavailable.

Symptoms:
- service_health == 0
- scrape failures in Prometheus
- 503 service crash injected

Remediation:
- restart_service for the crashed instance
- Investigate crash flag or OOM (memory stress scenario)
"""
