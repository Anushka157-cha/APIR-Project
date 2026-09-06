# APIR Deterministic Live Demo Guide

This guide provides a reproducible, end-to-end walkthrough of the APIR platform on a live Docker microservices stack. Every step uses real Prometheus metrics, real Docker container events, and real PostgreSQL database rows.

---

## 1. Prerequisites & Environment Setup

Ensure Docker and Docker Compose are installed:
```powershell
# Navigate to the APIR repository
cd apir

# Start the complete 12-container distributed stack
docker compose up -d

# Verify all containers are running and healthy
docker compose ps
```

The stack exposes:
- **SRE Dashboard**: [http://localhost:3000](http://localhost:3000)
- **Control Plane API**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus Metrics**: [http://localhost:9090](http://localhost:9090)
- **Grafana Visualizations**: [http://localhost:3001](http://localhost:3001)

---

## 2. End-to-End Incident Walkthrough: Payment Latency Cascade

### Step 1: Login to the SRE Control Console
1. Navigate to `http://localhost:3000`.
2. Login with credentials:
   - Username: `sre`
   - Password: `sre123`
3. Observe the **System Health Matrix** showing `100 HEALTHY` across all 5 microservices (`gateway`, `order-service`, `payment-service`, `inventory-service`, `notification-service`).

### Step 2: Inject Payment Service Latency
Via the UI (or API), inject 2000ms latency into `payment-service`:
```powershell
# Authenticate and obtain JWT
$login = Invoke-RestMethod -Uri http://localhost:8000/auth/login `
    -Method POST `
    -Body (@{username="sre";password="sre123"} | ConvertTo-Json) `
    -ContentType "application/json"
$token = $login.access_token

# Trigger FAIL_PAYMENT_LATENCY
Invoke-RestMethod -Uri http://localhost:8000/failures/FAIL_PAYMENT_LATENCY/start `
    -Method POST `
    -Headers @{"Authorization"="Bearer $token"} `
    -ContentType "application/json"
```

### Step 3: Generate Real Distributed Traffic
Send checkout transactions through the API gateway. The gateway routes to `order-service`, which synchronously calls `payment-service`:
```powershell
$body = @{
    user_id="user_sre_demo"
    items=@(@{product_id="P100";quantity=1})
    payment_method="card"
} | ConvertTo-Json

for ($i=1; $i -le 12; $i++) {
    try {
        Invoke-WebRequest -Uri http://localhost:8080/orders `
            -Method POST `
            -Body $body `
            -ContentType "application/json" `
            -TimeoutSec 10 | Out-Null
        Write-Host "Transaction $i completed (latency ~2200ms)"
    } catch {
        Write-Host "Transaction $i timed out"
    }
    Start-Sleep -Milliseconds 400
}
```

### Step 4: Multi-Signal Anomaly Detection
1. Within 15–30 seconds, Prometheus scrapes the histogram buckets for `request_latency_seconds_bucket`.
2. The APIR Detection Engine evaluates the sliding window:
   - P95 latency jumps from ~45ms to > 2400ms (threshold: 800ms).
   - Z-score exceeds 3.0 standard deviations.
   - EWMA confirms sustained divergence.
3. The engine creates an incident with:
   - **Fingerprint**: `payment-service:latency_spike:p95_ms`
   - **Composite Anomaly Score**: ~0.75 / 1.0 (with contributor weights: latency 0.35, z-score 0.10, error rate 0.0).

### Step 5: Dependency-Aware Causal RCA
1. Navigate to the incident details page (`/incidents/{id}`).
2. Click **Run Investigation** (or observe automatic background RCA).
3. The causal graph algorithm inspects topology:
   - `payment-service`: Acute latency onset, no degraded dependencies $\to$ Classified as `ROOT_CAUSE_ORIGIN`.
   - `order-service` and `gateway`: Elevated latency as direct callers $\to$ Tagged as `DOWNSTREAM_VICTIM` with explicit causal narrative.
4. Top Ranked Hypothesis: `"payment service injected or handler latency"` (Confidence: ~85%).

### Step 6: Blast Radius & Remediation Policy Gate
1. The blast radius engine traverses the dependency graph:
   - Target: `payment-service`
   - Dependent Callers: `order-service`, `gateway`
   - Impact Tier: `MEDIUM` (3 affected services)
2. Policy evaluation:
   - Proposed Action: `restart_service` (risk: `LOW`)
   - Decision: `AUTO_EXECUTE` (or `REQUIRE_APPROVAL` based on operator policy config)

### Step 7: Safe Execution & Multi-Sample Verification
1. Operator approves remediation (or automated policy triggers execution).
2. The control plane clears failure flags in Redis and restarts the `payment-service` Docker container.
3. Multi-Sample Telemetry Verification initiates:
   - Collects 4 consecutive Prometheus samples at 3s intervals.
   - Confirms latency drops below 800ms and health remains 1.0.
   - Recovery Percentage: 100%.
   - Incident transitions to `RESOLVED`.

### Step 8: Verifiable Lifecycle Timeline
The UI displays the full timestamped audit sequence:
- `FAILURE_INJECTED` $\to$ `METRIC_DETECTED` $\to$ `INCIDENT_DETECTED` $\to$ `INVESTIGATION_STARTED` $\to$ `RCA_COMPLETED` $\to$ `REMEDIATION_PROPOSED` $\to$ `APPROVAL_GRANTED` $\to$ `REMEDIATION_STARTED` $\to$ `REMEDIATION_COMPLETED` $\to$ `VERIFICATION_STARTED` $\to$ `VERIFICATION_PASSED` $\to$ `INCIDENT_RESOLVED`.

---

## 3. Incident Comparison Demo

1. Navigate to **Compare** (`/incidents/compare`).
2. Select two incidents from the dropdowns.
3. The side-by-side comparison displays:
   - Fingerprint match (detects recurring failure patterns)
   - Anomaly score comparison
   - RCA hypotheses and confidence comparison
   - MTTR duration comparison

---

## 4. Operational SRE Analytics Demo

Query real-time metrics dynamically calculated from PostgreSQL:
```powershell
$analytics = Invoke-RestMethod -Uri http://localhost:8000/analytics/operational `
    -Headers @{"Authorization"="Bearer $token"}
$analytics | ConvertTo-Json
```
Output:
- `mttd_seconds`: Real average detection duration
- `mttr_seconds`: Real average resolution duration
- `remediation_success_rate`: Percentage of executions verified successful
- `auto_remediation_rate`: Proportion of automated resolutions
- `rollback_rate`: Proportion of reverted remediations
