from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.action_registry import ALLOWED_ACTIONS, validate_action
from app.agents import investigate, propose_remediation
from app.analytics import compute_operational_analytics, compute_service_health_scores
from app.auth import create_token, get_current_user, require_roles, verify_password
from app.blast_radius import calculate_blast_radius
from app.config import settings
from app.db import get_session
from app.dependency_graph import SERVICES, downstream, react_flow, upstream
from app.executor import execute_action, rollback_action
from app.failures import SCENARIOS, list_active, start_scenario, stop_scenario
from app.prom import PrometheusClient
from app.state_machine import can_transition, transition_incident
from app.verification import verify_stabilized
from app.rag import ingest_knowledge, search as rag_search

router = APIRouter()
prom = PrometheusClient()


class LoginBody(BaseModel):
    username: str
    password: str


class IncidentUpdate(BaseModel):
    status: str | None = None
    severity: str | None = None
    description: str | None = None


class IncidentCreate(BaseModel):
    title: str
    description: str = ""
    severity: str = "MEDIUM"
    service: str
    incident_type: str = "manual"


class ApprovalBody(BaseModel):
    reason: str = ""


class ReplayBody(BaseModel):
    auto_approve: bool = False


class RAGIngestBody(BaseModel):
    reindex: bool = False


async def add_event(session: AsyncSession, incident_id: str, event_type: str, payload: dict | None = None) -> None:
    await session.execute(
        text(
            "INSERT INTO incident_events (incident_id, event_type, payload) VALUES (:id, :t, :p)"
        ),
        {"id": incident_id, "t": event_type, "p": json.dumps(payload or {})},
    )


async def audit(session: AsyncSession, user: dict | None, action: str, **kwargs) -> None:
    await session.execute(
        text(
            """
            INSERT INTO audit_logs (username, action, target, incident_id, approval, result, reason)
            VALUES (:u, :a, :t, :i, :ap, :r, :reason)
            """
        ),
        {
            "u": (user or {}).get("username"),
            "a": action,
            "t": kwargs.get("target"),
            "i": kwargs.get("incident_id"),
            "ap": kwargs.get("approval"),
            "r": kwargs.get("result"),
            "reason": kwargs.get("reason"),
        },
    )


@router.post("/auth/login")
async def login(body: LoginBody, session: AsyncSession = Depends(get_session)):
    row = (
        await session.execute(
            text("SELECT username, password_hash, role FROM users WHERE username=:u"),
            {"u": body.username},
        )
    ).mappings().first()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "invalid credentials")
    token = create_token(row["username"], row["role"])
    return {"access_token": token, "token_type": "bearer", "role": row["role"], "username": row["username"]}


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.get("/dashboard")
async def dashboard(session: AsyncSession = Depends(get_session), user: dict = Depends(get_current_user)):
    snap = await prom.snapshot()
    incidents = (
        await session.execute(
            text(
                """
                SELECT incident_id, title, severity, status, service, incident_type, detected_at, resolved_at
                FROM incidents ORDER BY detected_at DESC LIMIT 20
                """
            )
        )
    ).mappings().all()
    open_rows = [i for i in incidents if i["status"] not in {"RESOLVED", "FAILED"}]
    critical = [i for i in open_rows if i["severity"] == "CRITICAL"]
    healthy = [s for s, m in snap.items() if (m.get("health") or 1) >= 1]
    unhealthy = [s for s in SERVICES if s not in healthy]
    p95s = [m.get("p95_ms") or 0 for m in snap.values()]
    err_rates = [m.get("error_rate") or 0 for m in snap.values()]
    mttr_row = (
        await session.execute(
            text(
                """
                SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - detected_at))) AS mttr
                FROM incidents WHERE resolved_at IS NOT NULL
                """
            )
        )
    ).mappings().first()
    return {
        "active_incidents": len(open_rows),
        "critical_incidents": len(critical),
        "healthy_services": healthy,
        "unhealthy_services": unhealthy,
        "error_rate": round(sum(err_rates) / len(err_rates), 4) if err_rates else 0,
        "p95_latency": round(max(p95s) if p95s else 0, 2),
        "mttr_seconds": round(float(mttr_row["mttr"] or 0), 2),
        "recent_incidents": [dict(i) for i in incidents],
        "snapshot": snap,
    }


@router.get("/incidents")
async def list_incidents(session: AsyncSession = Depends(get_session), user: dict = Depends(get_current_user)):
    rows = (
        await session.execute(text("SELECT * FROM incidents ORDER BY detected_at DESC LIMIT 100"))
    ).mappings().all()
    return [dict(r) for r in rows]


@router.post("/incidents")
async def create_incident(
    body: IncidentCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_roles("ADMIN", "SRE")),
):
    iid = str(uuid.uuid4())
    await session.execute(
        text(
            """
            INSERT INTO incidents (incident_id, title, description, severity, status, service, incident_type, metadata)
            VALUES (:id, :title, :d, :sev, 'OPEN', :svc, :t, '{}')
            """
        ),
        {
            "id": iid,
            "title": body.title,
            "d": body.description,
            "sev": body.severity,
            "svc": body.service,
            "t": body.incident_type,
        },
    )
    await add_event(session, iid, "INCIDENT_DETECTED", {"manual": True})
    await session.commit()
    return {"incident_id": iid}


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    row = (
        await session.execute(text("SELECT * FROM incidents WHERE incident_id=:id"), {"id": incident_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, "not found")
    events = (
        await session.execute(
            text(
                "SELECT event_type, payload, created_at FROM incident_events WHERE incident_id=:id ORDER BY id"
            ),
            {"id": incident_id},
        )
    ).mappings().all()
    plans = (
        await session.execute(
            text("SELECT * FROM remediation_plans WHERE incident_id=:id ORDER BY created_at DESC"),
            {"id": incident_id},
        )
    ).mappings().all()
    executions = (
        await session.execute(text("SELECT e.* FROM remediation_executions e JOIN remediation_plans p ON p.id=e.plan_id WHERE p.incident_id=:id ORDER BY e.started_at DESC"), {"id": incident_id})
    ).mappings().all()

    timeline_events = []
    prev_time = None
    for ev in events:
        ev_dict = dict(ev)
        curr_time = ev_dict.get("created_at")
        if prev_time and curr_time:
            ev_dict["duration_since_prev_seconds"] = max(0.0, (curr_time - prev_time).total_seconds())
        else:
            ev_dict["duration_since_prev_seconds"] = 0.0
        prev_time = curr_time
        timeline_events.append(ev_dict)

    inc_meta = row.get("metadata") or {}
    if isinstance(inc_meta, str):
        try:
            inc_meta = json.loads(inc_meta)
        except Exception:
            inc_meta = {}

    explain_decision = inc_meta.get("intelligence", {}).get("explanation") or {
        "what": f"Incident on service {row['service']} ({row['incident_type']})",
        "why_detected": f"Observed metrics exceeded baseline anomaly threshold for {row['service']}",
        "why_rca": "Corroborated by topology and telemetry signals",
        "action_selection": "Allowlisted action selected based on service runbook and risk assessment",
        "policy_decision": "Evaluated against risk, blast radius, and historical remediation rate",
        "verification_outcome": "Health samples evaluated post-remediation",
        "final_state": row["status"],
    }

    return {
        "incident": dict(row),
        "events": timeline_events,
        "timeline": timeline_events,
        "plans": [dict(p) for p in plans],
        "executions": [dict(e) for e in executions],
        "explain_decision": explain_decision,
        "intelligence": inc_meta.get("intelligence"),
        "blast_radius": inc_meta.get("blast_radius"),
    }


@router.patch("/incidents/{incident_id}")
async def patch_incident(
    incident_id: str,
    body: IncidentUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_roles("ADMIN", "SRE")),
):
    row = (
        await session.execute(text("SELECT * FROM incidents WHERE incident_id=:id"), {"id": incident_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, "not found")
    status = body.status or row["status"]
    await session.execute(
        text(
            """
            UPDATE incidents SET status=:s, severity=COALESCE(:sev, severity), description=COALESCE(:d, description),
            resolved_at = CASE WHEN :s IN ('RESOLVED','FAILED','PARTIALLY_RESOLVED') THEN NOW() ELSE resolved_at END
            WHERE incident_id=:id
            """
        ),
        {"s": status, "sev": body.severity, "d": body.description, "id": incident_id},
    )
    await session.commit()
    return {"ok": True}


@router.get("/incidents/{incident_id}/timeline")
async def timeline(
    incident_id: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    rows = (
        await session.execute(
            text(
                "SELECT event_type, payload, created_at FROM incident_events WHERE incident_id=:id ORDER BY id"
            ),
            {"id": incident_id},
        )
    ).mappings().all()
    timeline_events = []
    prev_time = None
    for ev in rows:
        ev_dict = dict(ev)
        curr_time = ev_dict.get("created_at")
        if prev_time and curr_time:
            ev_dict["duration_since_prev_seconds"] = max(0.0, (curr_time - prev_time).total_seconds())
        else:
            ev_dict["duration_since_prev_seconds"] = 0.0
        prev_time = curr_time
        timeline_events.append(ev_dict)
    return timeline_events


@router.post("/incidents/{incident_id}/investigate")
async def run_investigate(
    incident_id: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_roles("ADMIN", "SRE")),
):
    row = (
        await session.execute(text("SELECT * FROM incidents WHERE incident_id=:id"), {"id": incident_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, "not found")
    await session.execute(
        text("UPDATE incidents SET status='INVESTIGATING' WHERE incident_id=:id"), {"id": incident_id}
    )
    await add_event(session, incident_id, "INVESTIGATION_STARTED")
    await session.commit()
    result = await investigate(session, dict(row))
    await add_event(session, incident_id, "EVIDENCE_COLLECTED", {"log_patterns": len(result["logs"])})
    await add_event(session, incident_id, "RCA_STARTED")
    await add_event(session, incident_id, "RCA_COMPLETED", {"top": (result["rca"].get("hypotheses") or [{}])[0]})
    plan = propose_remediation(dict(row), result["rca"])
    pid = str(uuid.uuid4())
    await session.execute(
        text(
            """
            INSERT INTO remediation_plans
            (id, incident_id, action_id, target, reason, risk, expected_effect, rollback_plan, status)
            VALUES (:id, :iid, :a, :t, :r, :risk, :e, :rb, 'proposed')
            """
        ),
        {
            "id": pid,
            "iid": incident_id,
            "a": plan["action"],
            "t": plan["target"],
            "r": plan["reason"],
            "risk": plan["risk"],
            "e": plan["expected_effect"],
            "rb": plan["rollback_plan"],
        },
    )
    await add_event(session, incident_id, "REMEDIATION_PROPOSED", plan)
    await add_event(session, incident_id, "APPROVAL_REQUESTED", {"plan_id": pid, "risk": plan["risk"]})
    meta = dict(row["metadata"] or {})
    if isinstance(row["metadata"], str):
        meta = json.loads(row["metadata"])
    meta["investigation"] = result
    meta["remediation_plan_id"] = pid
    await session.execute(
        text("UPDATE incidents SET status='MITIGATING', metadata=:m WHERE incident_id=:id"),
        {"m": json.dumps(meta, default=str), "id": incident_id},
    )
    await session.commit()
    if plan["risk"] == "LOW" and settings.auto_execute_low_risk:
        await _execute_plan(session, pid, user, auto=True)
    return {"investigation": result, "remediation": {**plan, "plan_id": pid}}


@router.get("/incidents/{incident_id}/impact")
async def incident_impact(
    incident_id: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    row = (
        await session.execute(text("SELECT service FROM incidents WHERE incident_id=:id"), {"id": incident_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, "not found")
    svc = row["service"]
    return {"service": svc, "upstream": upstream(svc), "downstream": downstream(svc), "graph": react_flow()}


async def _execute_plan(session: AsyncSession, plan_id: str, user: dict, auto: bool = False) -> dict:
    plan = (
        await session.execute(text("SELECT * FROM remediation_plans WHERE id=:id"), {"id": plan_id})
    ).mappings().first()
    if not plan:
        raise HTTPException(404, "plan not found")
    if plan["risk"] == "CRITICAL":
        raise HTTPException(400, "CRITICAL actions cannot be executed automatically")
    spec = validate_action(plan["action_id"], plan["target"])
    if user.get("role") not in spec["required_permissions"]:
        raise HTTPException(403, "role is not permitted for this action")
    # Atomic transition prevents concurrent approval/execution requests from running twice.
    required_state = "proposed" if auto else "approved"
    transition = await session.execute(
        text("UPDATE remediation_plans SET status='executing' WHERE id=:id AND status=:state RETURNING id"),
        {"id": plan_id, "state": required_state},
    )
    if not transition.first():
        raise HTTPException(409, "plan is not eligible for execution")
    await session.commit()
    before = await prom.snapshot()
    await add_event(session, plan["incident_id"], "REMEDIATION_STARTED", {"plan_id": plan_id})
    result = await execute_action(plan["action_id"], plan["target"])
    eid = str(uuid.uuid4())
    await session.execute(
        text(
            """
            INSERT INTO remediation_executions (id, plan_id, approved_by, result, details, finished_at)
            VALUES (:id, :p, :u, :r, :d, NOW())
            """
        ),
        {
            "id": eid,
            "p": plan_id,
            "u": user.get("username"),
            "r": "ok" if result.get("ok") else "failed",
            "d": json.dumps(result, default=str),
        },
    )
    await session.execute(text("UPDATE remediation_plans SET status=:s WHERE id=:id"), {"s": "executed" if result.get("ok") else "failed", "id": plan_id})
    await add_event(session, plan["incident_id"], "REMEDIATION_COMPLETED", result)
    await add_event(session, plan["incident_id"], "VERIFICATION_STARTED")
    after = await prom.snapshot()
    verification = await verify_stabilized(before, plan["target"], prom=prom) if result.get("ok") else {"status": "FAILED", "before": before.get(plan["target"], {}), "after": after.get(plan["target"], {}), "checks": {"execution_ok": False}, "samples_used": 0, "recovery_percentage": 0}
    inc_status = "RESOLVED" if verification["status"] in {"RESOLVED", "PARTIALLY_RESOLVED"} else "FAILED"
    await session.execute(
        text("UPDATE incidents SET status=:s, resolved_at=NOW() WHERE incident_id=:id"),
        {"s": inc_status, "id": plan["incident_id"]},
    )
    event = "RESOLVED" if inc_status == "RESOLVED" else "FAILED"
    await add_event(session, plan["incident_id"], event, verification)
    if inc_status == "RESOLVED":
        await add_event(session, plan["incident_id"], "VERIFICATION_PASSED", verification)
        await add_event(session, plan["incident_id"], "INCIDENT_RESOLVED", {"status": "RESOLVED"})
    else:
        await add_event(session, plan["incident_id"], "VERIFICATION_FAILED", verification)
    await audit(
        session,
        user,
        plan["action_id"],
        target=plan["target"],
        incident_id=plan["incident_id"],
        approval="auto" if auto else "granted",
        result=verification["status"],
        reason=plan["reason"],
    )
    await session.commit()
    return {"execution_id": eid, "verification": verification, "result": result}


@router.post("/remediation/{plan_id}/approve")
async def approve(
    plan_id: str,
    body: ApprovalBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_roles("ADMIN", "SRE")),
):
    plan = (
        await session.execute(text("SELECT * FROM remediation_plans WHERE id=:id"), {"id": plan_id})
    ).mappings().first()
    if not plan:
        raise HTTPException(404, "not found")
    if plan["risk"] == "CRITICAL":
        raise HTTPException(403, "CRITICAL risk cannot be approved for execution in this system")
    spec = validate_action(plan["action_id"], plan["target"])
    if user["role"] not in spec["required_permissions"]:
        raise HTTPException(403, "role is not permitted for this action")
    changed = await session.execute(text("UPDATE remediation_plans SET status='approved' WHERE id=:id AND status='proposed' RETURNING id"), {"id": plan_id})
    if not changed.first():
        raise HTTPException(409, "plan is no longer awaiting approval")
    await add_event(session, plan["incident_id"], "APPROVAL_GRANTED", {"by": user["username"], "reason": body.reason})
    await session.commit()
    return await _execute_plan(session, plan_id, user, auto=False)


@router.post("/remediation/{plan_id}/reject")
async def reject(
    plan_id: str,
    body: ApprovalBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_roles("ADMIN", "SRE")),
):
    plan = (
        await session.execute(text("SELECT * FROM remediation_plans WHERE id=:id"), {"id": plan_id})
    ).mappings().first()
    if not plan:
        raise HTTPException(404, "not found")
    changed = await session.execute(text("UPDATE remediation_plans SET status='rejected' WHERE id=:id AND status='proposed' RETURNING id"), {"id": plan_id})
    if not changed.first():
        raise HTTPException(409, "plan is no longer awaiting a decision")
    await audit(session, user, "reject", target=plan["target"], incident_id=plan["incident_id"], approval="rejected", result="rejected", reason=body.reason)
    await session.commit()
    return {"ok": True}


@router.post("/remediation/{execution_id}/rollback")
async def rollback(
    execution_id: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_roles("ADMIN", "SRE")),
):
    exec_row = (
        await session.execute(
            text(
                """
                SELECT e.*, p.target, p.action_id, p.incident_id 
                FROM remediation_executions e 
                JOIN remediation_plans p ON p.id=e.plan_id 
                WHERE e.id=:id
                """
            ),
            {"id": execution_id},
        )
    ).mappings().first()
    if not exec_row:
        raise HTTPException(404, "execution not found")

    incident_id = exec_row["incident_id"]
    target = exec_row["target"]

    await add_event(session, incident_id, "ROLLBACK_STARTED", {"execution_id": execution_id, "target": target})
    rb_result = await rollback_action(execution_id, target)
    
    status_str = "ROLLED_BACK" if rb_result.get("ok") else "ROLLBACK_FAILED"
    await session.execute(
        text("UPDATE incidents SET status=:s WHERE incident_id=:id"),
        {"s": status_str, "id": incident_id},
    )
    await add_event(session, incident_id, "ROLLBACK_COMPLETED", rb_result)
    await audit(
        session,
        user,
        "rollback",
        target=target,
        incident_id=incident_id,
        approval="operator",
        result=status_str,
        reason=f"Rollback initiated for execution {execution_id}",
    )
    await session.commit()
    return {"ok": rb_result.get("ok"), "status": status_str, "details": rb_result}


@router.get("/analytics/operational")
async def operational_analytics(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    return await compute_operational_analytics(session)


@router.get("/health/system")
async def system_health(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    snapshot = await prom.snapshot()
    return compute_service_health_scores(snapshot)


@router.get("/incidents/compare")
async def compare_incidents(
    a: str,
    b: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    row_a = (
        await session.execute(text("SELECT * FROM incidents WHERE incident_id=:id"), {"id": a})
    ).mappings().first()
    row_b = (
        await session.execute(text("SELECT * FROM incidents WHERE incident_id=:id"), {"id": b})
    ).mappings().first()
    if not row_a or not row_b:
        raise HTTPException(404, "one or both incidents not found")

    def parse_meta(meta):
        if not meta:
            return {}
        if isinstance(meta, str):
            try:
                return json.loads(meta)
            except Exception:
                return {}
        return dict(meta)

    meta_a = parse_meta(row_a["metadata"])
    meta_b = parse_meta(row_b["metadata"])

    def calc_resolution_time(row):
        if row["detected_at"] and row["resolved_at"]:
            return max(0.0, (row["resolved_at"] - row["detected_at"]).total_seconds())
        return None

    intel_a = meta_a.get("intelligence", {})
    intel_b = meta_b.get("intelligence", {})

    return {
        "incident_a": {
            "incident_id": row_a["incident_id"],
            "service": row_a["service"],
            "incident_type": row_a["incident_type"],
            "severity": row_a["severity"],
            "status": row_a["status"],
            "anomaly_score": intel_a.get("anomaly_score", row_a.get("incident_score")),
            "rca_confidence": intel_a.get("confidence_score", row_a.get("confidence_score")),
            "root_cause": intel_a.get("selected_root_cause") or row_a.get("root_cause") or row_a["service"],
            "resolution_time_seconds": calc_resolution_time(row_a),
            "blast_radius": meta_a.get("blast_radius", {}).get("risk_category", "LOW"),
            "fingerprint": intel_a.get("fingerprint"),
        },
        "incident_b": {
            "incident_id": row_b["incident_id"],
            "service": row_b["service"],
            "incident_type": row_b["incident_type"],
            "severity": row_b["severity"],
            "status": row_b["status"],
            "anomaly_score": intel_b.get("anomaly_score", row_b.get("incident_score")),
            "rca_confidence": intel_b.get("confidence_score", row_b.get("confidence_score")),
            "root_cause": intel_b.get("selected_root_cause") or row_b.get("root_cause") or row_b["service"],
            "resolution_time_seconds": calc_resolution_time(row_b),
            "blast_radius": meta_b.get("blast_radius", {}).get("risk_category", "LOW"),
            "fingerprint": intel_b.get("fingerprint"),
        },
        "comparison": {
            "same_service": row_a["service"] == row_b["service"],
            "same_type": row_a["incident_type"] == row_b["incident_type"],
            "is_recurrence": intel_a.get("fingerprint") is not None and intel_a.get("fingerprint") == intel_b.get("fingerprint"),
        }
    }


@router.get("/dependency-graph")
async def dep_graph(user: dict = Depends(get_current_user)):
    snap = await prom.snapshot()
    health = {k: ("healthy" if (v.get("health") or 1) >= 1 else "unhealthy") for k, v in snap.items()}
    return {**react_flow(health), "snapshot": snap}


@router.get("/services")
async def services(user: dict = Depends(get_current_user)):
    snap = await prom.snapshot()
    return [{"name": s, **(snap.get(s) or {})} for s in SERVICES]


@router.post("/rag/ingest")
async def rag_ingest(body: RAGIngestBody, session: AsyncSession = Depends(get_session), user: dict = Depends(require_roles("ADMIN", "SRE"))):
    count = await ingest_knowledge(session, reindex=body.reindex)
    await audit(session, user, "rag_ingest", result="ok", reason="reindex" if body.reindex else "incremental")
    await session.commit()
    return {"indexed_chunks": count, "mode": "reindex" if body.reindex else "incremental", "embedding": "hashed-local lexical fallback"}


@router.get("/rag/search")
async def rag_query(q: str, source: str | None = None, limit: int = 5, session: AsyncSession = Depends(get_session), user: dict = Depends(get_current_user)):
    if not q.strip():
        raise HTTPException(422, "q must not be empty")
    return {"query": q, "results": await rag_search(session, q, source=source, limit=max(1, min(limit, 20))), "embedding": "hashed-local lexical fallback"}


@router.get("/services/{service}/dependencies")
async def service_deps(service: str, user: dict = Depends(get_current_user)):
    if service not in SERVICES:
        raise HTTPException(404, "unknown service")
    return {"service": service, "upstream": upstream(service), "downstream": downstream(service)}


@router.get("/failures")
async def failures(user: dict = Depends(get_current_user)):
    try:
        active = await list_active()
    except Exception:
        active = []
    return {"scenarios": SCENARIOS, "active": active}


@router.post("/failures/{scenario}/start")
async def fail_start(
    scenario: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_roles("ADMIN", "SRE")),
):
    try:
        result = await start_scenario(scenario)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await session.execute(
        text("INSERT INTO failure_events (scenario, target, action, metadata) VALUES (:s, :t, 'start', '{}')"),
        {"s": scenario, "t": result.get("target")},
    )
    await audit(session, user, "failure_start", target=result.get("target"), result="started", reason=scenario)
    await session.commit()
    return result


@router.post("/failures/{scenario}/stop")
async def fail_stop(
    scenario: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_roles("ADMIN", "SRE")),
):
    try:
        result = await stop_scenario(scenario)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await session.execute(
        text("INSERT INTO failure_events (scenario, target, action, stopped_at) VALUES (:s, :t, 'stop', NOW())"),
        {"s": scenario, "t": result.get("target")},
    )
    await session.commit()
    return result


@router.get("/audit-logs")
async def audit_logs(session: AsyncSession = Depends(get_session), user: dict = Depends(require_roles("ADMIN", "SRE"))):
    rows = (await session.execute(text("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 200"))).mappings().all()
    return [dict(r) for r in rows]


@router.get("/evaluation")
async def evaluation(session: AsyncSession = Depends(get_session), user: dict = Depends(get_current_user)):
    rows = (await session.execute(text("SELECT * FROM evaluation_runs ORDER BY started_at DESC"))).mappings().all()
    runs = [dict(r) for r in rows]
    n = len(runs) or 1
    finished = [r for r in runs if r.get("finished_at")]
    def avg(key):
        vals = [r[key] for r in finished if r.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0
    def rate(key):
        vals = [r[key] for r in finished if r.get(key) is not None]
        return round(sum(1 for v in vals if v) / len(vals), 3) if vals else 0
    return {
        "runs": runs,
        "summary": {
            "detection_accuracy": rate("rca_correct") if False else _detection_accuracy(finished),
            "rca_accuracy": rate("rca_correct"),
            "mttd_ms": avg("detection_ms"),
            "mtti_ms": avg("investigation_ms"),
            "mttr_ms": avg("resolution_ms"),
            "remediation_success_rate": rate("remediation_success"),
            "false_positive_rate": rate("false_positive"),
            "n": len(finished),
        },
    }


def _detection_accuracy(runs: list[dict]) -> float:
    if not runs:
        return 0.0
    detected = [r for r in runs if r.get("incident_id")]
    return round(len(detected) / len(runs), 3)


@router.get("/evaluation/{incident_id}")
async def evaluation_one(
    incident_id: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    row = (
        await session.execute(text("SELECT * FROM evaluation_runs WHERE incident_id=:id"), {"id": incident_id})
    ).mappings().first()
    if not row:
        raise HTTPException(404, "not found")
    return dict(row)


@router.get("/actions")
async def actions(user: dict = Depends(get_current_user)):
    return ALLOWED_ACTIONS


@router.post("/replay/{scenario}")
async def replay(
    scenario: str,
    body: ReplayBody,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(require_roles("ADMIN", "SRE")),
):
    import asyncio
    import httpx
    from app.detection import DetectionEngine

    if scenario not in SCENARIOS:
        raise HTTPException(400, "unknown scenario")
    run_id = str(uuid.uuid4())
    t0 = datetime.now(timezone.utc)
    await session.execute(
        text("INSERT INTO evaluation_runs (id, scenario) VALUES (:id, :s)"),
        {"id": run_id, "s": scenario},
    )
    await session.commit()
    await start_scenario(scenario)
    gateway = "http://gateway:8080"
    async with httpx.AsyncClient(timeout=10) as client:
        for _ in range(12):
            try:
                await client.post(
                    f"{gateway}/orders",
                    json={"user_id": "user123", "items": [{"product_id": "P001", "quantity": 1}], "payment_method": "card"},
                )
            except Exception:
                pass
            await asyncio.sleep(0.4)
    detector = DetectionEngine()
    created = await detector.tick(session)
    spec = SCENARIOS[scenario]
    incident = next((c for c in created if c["service"] == spec["target"]), created[0] if created else None)
    detection_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    rca_ok = False
    rem_ok = False
    inv_ms = None
    res_ms = None
    iid = None
    if incident:
        iid = incident["incident_id"]
        inv_start = datetime.now(timezone.utc)
        inv = await run_investigate(iid, session, user)  # type: ignore[arg-type]
        inv_ms = int((datetime.now(timezone.utc) - inv_start).total_seconds() * 1000)
        top = ((inv.get("investigation") or {}).get("rca") or {}).get("hypotheses") or [{}]
        top_name = (top[0].get("hypothesis") or "").lower()
        rca_ok = spec["expected_root_cause"].split()[0].lower() in top_name or spec["expected_root_cause"].lower() in top_name
        if body.auto_approve:
            plan_id = inv["remediation"]["plan_id"]
            try:
                exec_result = await approve(plan_id, ApprovalBody(reason="replay approval"), session, user)
                rem_ok = exec_result["verification"]["status"] in {"RESOLVED", "PARTIALLY_RESOLVED"}
            except Exception:
                rem_ok = False
        res_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    await stop_scenario(scenario)
    await session.execute(
        text(
            """
            UPDATE evaluation_runs SET finished_at=NOW(), incident_id=:iid, detection_ms=:d,
            investigation_ms=:i, resolution_ms=:r, rca_correct=:rca, remediation_success=:rem,
            false_positive=:fp WHERE id=:id
            """
        ),
        {
            "iid": iid,
            "d": detection_ms,
            "i": inv_ms,
            "r": res_ms,
            "rca": rca_ok,
            "rem": rem_ok,
            "fp": incident is None,
            "id": run_id,
        },
    )
    await session.commit()
    row = (await session.execute(text("SELECT * FROM evaluation_runs WHERE id=:id"), {"id": run_id})).mappings().first()
    return dict(row)


@router.post("/actions/execute")
async def raw_execute(user: dict = Depends(require_roles("ADMIN"))):
    raise HTTPException(400, "arbitrary actions rejected; use remediation approval flow")
