"""Inventory service failure.

Symptoms:
- POST /reserve returns 5xx or 503
- orders fail before payment
- inventory-service health is down or crash flag is set

Remediation:
- Restart inventory-service
- Confirm PostgreSQL is reachable
- Check stock lock contention in logs
"""
