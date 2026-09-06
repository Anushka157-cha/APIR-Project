"""Database connection pool exhaustion.

Signals:
- logs containing "database connection pool exhaustion" or "too many clients"
- database_latency histogram climbing while request volume is flat
- payment or inventory handlers blocking before SQL executes

Remediation:
- Restart the affected service to drop leaked connections (LOW)
- Reduce injected pool_exhaust failure flags in development
- Increase pool size only after confirming leak vs capacity

Do not run arbitrary SQL from the incident agent.
"""
