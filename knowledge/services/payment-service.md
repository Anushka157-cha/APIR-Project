# payment-service

Handles capture of order payments. Depends on PostgreSQL.
Exposes POST /payments and Prometheus metrics on /metrics.

SLO: p95 < 400ms under normal load.
Critical dependency for checkout.
