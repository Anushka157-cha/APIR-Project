"""Payment latency spike — runbook.

Symptoms:
- payment-service request_latency p95 rises above 800ms
- checkout errors increase at the API gateway
- order-service waits on /payments

Likely causes (check in order):
1. Injected or accidental handler delay
2. Database connection pool exhaustion (look for pool wait logs, db latency)
3. Downstream network delay to PostgreSQL
4. Recent payment-service deployment

Safe remediations:
- Restart payment-service (LOW risk) after confirming no in-flight schema migration
- Rollback the last payment deploy if the spike started at deploy time
- Do not scale blindly if the bottleneck is the database

Verification:
- p95 latency returns near baseline
- 5xx rate < 1%
"""
