# APIR — Autonomous Production Incident Resolver

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14.2-black.svg)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**APIR** is an enterprise-grade, deterministic Site Reliability Engineering (SRE) and Autonomous Incident Resolution control plane. It operates on a real multi-tier distributed microservice architecture instrumented with Prometheus, OpenTelemetry, PostgreSQL, and Redis.

Rather than treating automated incident resolution as a naive script or an unconstrained LLM chatbot, APIR demonstrates the rigorous, safety-first engineering required for automated operations:
**Observability → Statistical Anomaly Detection → Dependency-Aware Causal RCA → Risk Assessment & Blast Radius → Safe Remediation → Multi-Sample Verification → Rollback → Auditability → Verifiable Operational Analytics**.

---

## Why APIR is Different

| Dimension | Traditional Monitoring / Toy Bots | APIR Autonomous Production Incident Resolver |
| :--- | :--- | :--- |
| **Telemetry & Detection** | Static single-metric alerts with noisy thresholds. | **Deterministic multi-signal composite scoring** (`p95_latency`, `error_rate`, `service_health`, `z_score`, `database_dependency`) with explicit contributor breakdown and fingerprint deduplication. |
| **Root Cause Analysis** | Blames whatever service fires first or lets an unconstrained LLM hallucinate causes. | **Causal & topology-aware propagation analysis**. Distinguishes leaf callee root causes from upstream caller victims in the call graph. |
| **Confidence Scoring** | Opaque percentage or subjective probability. | **Mathematical confidence calibration** summing metric evidence (+0.35), dependency causality (+0.25), temporal precedence (+0.25), runbooks (+0.20), logs (+0.10), and contradiction penalties (-0.12). |
| **Blast Radius Analysis** | Remediation executed blindly on target. | **Topology graph traversal** determining target, dependent callers, affected count, and impact tier (`LOW`, `MEDIUM`, `HIGH`) before execution. |
| **Remediation Safety** | Arbitrary shell execution or binary auto-pilot. | **Risk-aware policy engine** (`AUTO_EXECUTE` vs `REQUIRE_APPROVAL` vs `REJECT`) with action allowlists, RBAC, execution timeouts, dry-run mode, and concurrency guards. |
| **Verification & Rollback** | Fire-and-forget execution. | **Multi-sample telemetry stabilization check** requiring $N$ consecutive healthy Prometheus samples, plus one-click operator rollback. |
| **Operational Analytics** | Hardcoded demo dashboard cards. | **Dynamically computed SRE metrics** from PostgreSQL: MTTD, MTTR, auto-remediation rate, rollback rate, and failure recurrence detection. |
| **Auditability** | Ephemeral console prints. | **Append-only immutable audit trail** and state transitions recording actor (`SYSTEM` vs `HUMAN`), target, action, reason, and results. |

---

## Architectural Overview

```
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                           APIR System Architecture                            │
 └─────────────────────────────────────────────────────────────────────────────┘

 ┌────────────────┐       ┌────────────────┐       ┌────────────────┐
 │   Next.js 14   │       │    FastAPI     │       │   PostgreSQL   │
 │  SRE Dashboard │◄─────►│ Control Plane  │◄─────►│ Incident Store │
 │     :3000      │       │     :8000      │       │     :5432      │
 └────────────────┘       └────────┬───────┘       └────────────────┘
                                   │
                  ┌────────────────┴────────────────┐
                  │ Deterministic Intelligence Core │
                  │  - Multi-Signal Scoring Engine  │
                  │  - Causal Dependency RCA        │
                  │  - Blast Radius Estimator       │
                  │  - Risk Policy Gatekeeper       │
                  │  - Multi-Sample Verification    │
                  └────────────────┬────────────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           ▼                       ▼                       ▼
    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │ Redis Store │         │ Prometheus  │         │ OpenTelemetry│
    │ Failure/Logs│         │ Telemetry   │         │ Tracing     │
    │    :6379    │         │    :9090    │         │    :4318    │
    └─────────────┘         └──────┬──────┘         └─────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
   ┌───────────┐             ┌───────────┐             ┌───────────┐
   │  Gateway  │────────────►│   Order   │────────────►│  Payment  │
   │   :8080   │             │   :8081   │             │   :8082   │
   └───────────┘             └─────┬─────┘             └───────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
              ┌───────────┐                 ┌───────────┐
              │ Inventory │                 │Notification│
              │   :8083   │                 │   :8084   │
              └───────────┘                 └───────────┘
```

---

## Core Engineering Features

### 1. Incident Intelligence Engine
Every incident persists a deterministic intelligence record:
- **Fingerprint**: `{service}:{incident_type}:{primary_metric}` for deduplication and recurrence clustering.
- **Anomaly Score**: Continuous $[0.0, 1.0]$ composite score calculated from real Prometheus metric deviations:
  $$\text{Score} = w_{\text{lat}} \cdot S_{\text{lat}} + w_{\text{err}} \cdot S_{\text{err}} + w_{\text{health}} \cdot S_{\text{health}} + w_{\text{z}} \cdot S_{\text{z}} + w_{\text{db}} \cdot S_{\text{db}}$$
- **Contributor Breakdown**: Transparent weightings ($0.35$ latency, $0.25$ error rate, $0.20$ health, $0.10$ z-score, $0.10$ DB dependency).

### 2. Dependency-Aware Causal RCA
Downstream services in call chains are not misclassified as root causes.
- If `payment-service` latency spikes, callers `order-service` and `gateway` naturally experience elevated latency.
- The engine traverses the dependency topology: leaf callees with acute anomalies are classified as `ROOT_CAUSE_ORIGIN`, while callers are tagged as `DOWNSTREAM_VICTIM` with explicit causal narratives.

### 3. Risk-Aware Remediation Policy
Remediation decisions pass through a deterministic policy gate outputting exactly one decision:
- `AUTO_EXECUTE`: Low risk, high confidence ($\ge 0.85$), blast radius $\le 3$, rollback available, and auto-execute enabled.
- `REQUIRE_APPROVAL`: High risk, medium risk with large blast radius, lower confidence ($< 0.70$), or poor historical success rate ($< 50\%$).
- `REJECT`: Unregistered action, unauthorized target, or safety invariants violated.

### 4. Blast Radius Analysis
Before remediation, APIR inspects the real dependency graph to determine:
- Directly targeted service.
- Upstream caller dependencies that may fail during restarts.
- Impact tier: `LOW` (1 service), `MEDIUM` (2–3 services), `HIGH` ($>3$ services).

### 5. Multi-Sample Verification & Rollback
Remediation is only considered successful after multi-sample stabilization:
- Queries Prometheus for $N$ consecutive healthy intervals ($N \ge 3$).
- Asserts latency $\le$ threshold, error rate $\le$ baseline, and health $\ge 1.0$.
- One-click or automated safe rollback (`POST /remediation/{id}/rollback`) clears failure flags and restores previous stable state if verification fails.

### 6. Operational Analytics
SRE metrics calculated from real timestamps in PostgreSQL:
- **MTTD** (Mean Time to Detect): Time from failure onset to incident creation.
- **MTTR** (Mean Time to Resolve): Time from incident creation to verified resolution.
- **Auto-Remediation Rate**: Percentage of incidents safely resolved without human intervention.
- **Rollback Rate**: Percentage of remediations reverted.
- **System Health Matrix**: Real-time 0–100 health score with mathematical deduction explanations.

---

## Verification & Testing

All automated tests use real services, real Prometheus metrics, and live Docker containers.

```powershell
# Run the complete test suite
python -m unittest discover -s tests -t . -v
```

### Test Suite Breakdown:
1. `tests/e2e/test_payment_latency_docker.py`: Real end-to-end payment latency injection → Prometheus scrape → anomaly detection → RCA → plan approval → Docker restart → multi-sample verification → RESOLVED.
2. `tests/unit/test_incident_intelligence.py`: Deterministic anomaly scoring, fingerprinting, and contributor weights.
3. `tests/unit/test_causal_rca.py`: Root cause origin vs downstream victim topology classification and confidence breakdown.
4. `tests/unit/test_remediation_policy.py`: Policy evaluation (`AUTO_EXECUTE`, `REQUIRE_APPROVAL`, `REJECT`) and blast radius calculation.
5. `tests/unit/test_state_machine.py`: Incident state lifecycle enforcement and idempotency guards.
6. `tests/integration/test_operational_analytics.py`: Transparent health scoring and deduction breakdown.
7. `tests/integration/test_prom_baseline.py`: Prometheus range query baseline calculations.
8. `tests/security/test_action_security.py`: Action registry allowlist, unauthorized target rejection, and RBAC validation.
9. `tests/unit/test_stats_scoring.py`: EWMA, moving average, and z-score statistical validation.
10. `tests/unit/test_verification.py`: Multi-sample stabilization requirement.

---

## Quickstart & Local Execution

### 1. Start Infrastructure & Services
```powershell
docker compose up -d
docker compose ps
```

### 2. Access Dashboards
- **APIR SRE Console**: [http://localhost:3000](http://localhost:3000) (Credentials: `sre` / `sre123` or `admin` / `admin123`)
- **Control Plane API**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus UI**: [http://localhost:9090](http://localhost:9090)
- **Grafana Dashboards**: [http://localhost:3001](http://localhost:3001)

---

## Technical Honesty: Implemented vs Future Work

### Implemented in Current Release:
- Deterministic multi-signal anomaly scoring and fingerprinting.
- Dependency-graph-aware causal root-cause analysis distinguishing origins from callers.
- Mathematical confidence calibration with explicit evidence and contradiction terms.
- Operational blast radius calculation based on live topology.
- Policy engine with automated safety gates, allowlist enforcement, and RBAC.
- Multi-sample telemetry recovery verification.
- Safe action rollback via API and SRE console.
- Real-time operational analytics (MTTD, MTTR, recurrence tracking).
- Side-by-side incident comparison engine.
- 100% passing automated test suite with real Docker microservices.

### Future Work (Roadmap):
- eBPF-based kernel network packet drop detection.
- Distributed tracing span-level critical path regression detection.
- Kubernetes Operator custom resource definitions (CRD) for cloud-native deployment.
- Canary remediation with progressive percentage traffic shifting.
