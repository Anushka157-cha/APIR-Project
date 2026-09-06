# Architecture

APIR consists of five Python microservices, a FastAPI control plane, PostgreSQL for incidents and audit records, Redis for failure flags and structured logs, Prometheus for operational telemetry, Grafana for dashboards, and OpenTelemetry for traces. The control plane never executes LLM output: remediation runs only through the action registry.
