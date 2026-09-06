# APIR Architecture & System Specifications

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

## 1. Why APIR is Different

1. **Deterministic Multi-Signal Telemetry**: Rather than arbitrary threshold alerts, APIR computes a multi-signal continuous anomaly score $[0.0, 1.0]$ across latency, error rate jump, service availability, z-score deviation, and database dependency latency.
2. **Topology-Aware Causal Root Cause Analysis**: When downstream dependencies degrade (e.g. `payment-service` latency spike), upstream callers (`order-service`, `gateway`) exhibit secondary latency symptoms. APIR models the distributed call graph to distinguish the originating callee (`ROOT_CAUSE_ORIGIN`) from caller victims (`DOWNSTREAM_VICTIM`).
3. **Calibrated Explainable Confidence**: Confidence scores are not opaque probabilities. They represent a deterministic linear combination of metric signal magnitude ($+0.35$), topological depth ($+0.25$), temporal onset ($+0.25$), runbook correlation ($+0.20$), logs ($+0.10$), and contradiction penalties ($-0.12$).
4. **Blast Radius Analysis**: Before executing any remediation, APIR inspects the graph to determine affected caller services and categorizes operational impact into `LOW`, `MEDIUM`, or `HIGH`.
5. **Risk-Aware Policy Gatekeeper**: Actions evaluate against an explicit deterministic matrix:
   - `AUTO_EXECUTE`: Low risk, high confidence ($\ge 0.85$), blast radius $\le 3$, rollback available, auto-execute permitted.
   - `REQUIRE_APPROVAL`: High risk, medium risk with wide blast radius, low confidence ($< 0.70$), or poor historical success rate ($< 50\%$).
   - `REJECT`: Unregistered action or unauthorized target.
6. **Multi-Sample Telemetry Verification & Rollback**: Remediation must be corroborated by $N \ge 3$ consecutive healthy telemetry samples before transitioning to `RESOLVED`. If verification fails or regression occurs, one-click or automated rollback restores the target service.
7. **Verifiable Operational Analytics**: MTTD, MTTR, auto-remediation rate, and rollback rate are computed from PostgreSQL event timestamps rather than hardcoded mock figures.

---

## 2. Microservice Dependency Topology

The system models a high-throughput e-commerce distributed architecture:
- **Gateway (`gateway`)**: Edge reverse proxy and routing entrypoint.
- **Order Service (`order-service`)**: Orchestrates checkout transactions. Calls `payment-service`, `inventory-service`, and `notification-service`.
- **Payment Service (`payment-service`)**: Handles card transactions and database persistence.
- **Inventory Service (`inventory-service`)**: Manages product stock reservations and catalog locking.
- **Notification Service (`notification-service`)**: Sends asynchronous order notifications and customer alerts.

### Call Topology:
$$\text{Gateway} \longrightarrow \text{Order Service} \longrightarrow \begin{cases} \text{Payment Service} \\ \text{Inventory Service} \\ \text{Notification Service} \end{cases}$$

---

## 3. Mathematical Formulations

### Multi-Signal Anomaly Scoring
$$\text{Score} = w_{\text{lat}} \cdot S_{\text{lat}} + w_{\text{err}} \cdot S_{\text{err}} + w_{\text{health}} \cdot S_{\text{health}} + w_{\text{z}} \cdot S_{\text{z}} + w_{\text{db}} \cdot S_{\text{db}}$$
- $w_{\text{lat}} = 0.35$: P95 latency deviation above baseline.
- $w_{\text{err}} = 0.25$: Error rate relative to service SLA.
- $w_{\text{health}} = 0.20$: Service health metric ($0.0$ if crashed, $1.0$ if running).
- $w_{\text{z}} = 0.10$: Z-score statistical divergence: $Z = \frac{x - \mu}{\sigma}$.
- $w_{\text{db}} = 0.10$: Database connection latency / pool exhaustion.

### Confidence Calibration
$$\text{Confidence} = \text{clamp}\left(\sum C_{\text{evidence}} - P_{\text{contradictions}}, 0.20, 0.98\right)$$
- Metric Evidence: $0.10$ to $0.35$ based on relative change.
- Dependency Causality: $0.25$ if target is identified as the origin dependency.
- Temporal Precedence: $0.20$ if metric anomaly onset strictly precedes downstream callers.
- Runbook Correlation: $0.10$ to $0.20$ lexical cosine match with verified runbooks.
- Contradiction Penalty: $-0.12$ if attempting to blame a known downstream victim.

---

## 4. Incident Lifecycle State Machine

```
         [ DETECTED ]
              │
              ▼
       [ INVESTIGATING ]
              │
              ▼
        [ MITIGATING ] ◄────────────────┐
              │                         │
              ▼                         │ (Retry)
        [ VERIFYING ]                   │
         │         │                    │
 (Pass)  │         │ (Fail)             │
         ▼         ▼                    │
    [RESOLVED]  [ FAILED ] ─────────────┤
                   │                    │
                   ▼                    │
            [ ROLLING_BACK ]            │
                   │                    │
                   ▼                    │
            [ ROLLED_BACK ] ────────────┘
```

---

## 5. Security & Safety Invariants

- **Action Registry Allowlist**: Only explicitly registered actions (`restart_service`, `scale_service`, `rollback_service`, `enable_feature_flag`) can be executed. Arbitrary shell command execution is strictly prevented at the API gate.
- **RBAC**: Three discrete roles:
  - `VIEWER`: Read-only telemetry and incident inspection.
  - `SRE`: Incident investigation, low/medium risk action approval, operational analytics.
  - `ADMIN`: High-risk remediation approval, system-wide configuration, and emergency rollbacks.
- **Dry-Run Mode**: When `DRY_RUN_MODE=true`, remediations are simulated and recorded in audit logs without mutating running containers.
- **Execution Timeouts**: All container lifecycle actions are wrapped in asyncio timeouts (default 15s) to prevent hanging jobs.
- **Atomic Concurrency Guards**: DB row-level locks and atomic state transitions prevent race conditions where multiple operators or workers execute duplicate actions on the same plan.

---

## 6. Implementation Scope

### Implemented & Verified in v1.0:
- Full multi-tier containerized stack with real Prometheus, OpenTelemetry, Postgres, Redis, and microservices.
- Multi-signal anomaly detection with fingerprint deduplication.
- Causal RCA graph engine with downstream victim classification.
- Blast radius estimation and risk-aware policy evaluation.
- Multi-sample telemetry stabilization verification.
- Safe rollback mechanism.
- Complete operational SRE analytics (MTTD, MTTR, recurrence tracking).
- Side-by-side incident comparison engine.
- Passing unit, integration, security, and real Docker E2E test suites.

### Future Work:
- Extended chaos matrix with eBPF network packet injection.
- Tracing span duration regression scoring.
- Cloud-native Kubernetes CRD operator.
