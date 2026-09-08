from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.config import settings
from app.db import SessionLocal
from app.detection import DetectionEngine
from app.seed import seed

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger("apir")

detector = DetectionEngine()


async def detection_loop() -> None:
    await asyncio.sleep(5)
    while True:
        try:
            async with SessionLocal() as session:
                created = await detector.tick(session)
                for inc in created:
                    from app.api import add_event
                    logger.info(json.dumps({
                        "event": "incident_detected",
                        "incident_id": inc["incident_id"],
                        "service": inc["service"],
                        "severity": inc["severity"],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
                    # auto-kick investigation in background
                    asyncio.create_task(_auto_investigate(inc["incident_id"]))
        except Exception as e:
            logger.error(json.dumps({
                "event": "detection_loop_error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
        await asyncio.sleep(settings.detection_interval_seconds)


async def _auto_investigate(incident_id: str) -> None:
    await asyncio.sleep(2)
    try:
        async with SessionLocal() as session:
            from app.agents import investigate, propose_remediation
            from sqlalchemy import text
            import json
            import uuid
            from app.api import add_event

            row = (
                await session.execute(text("SELECT * FROM incidents WHERE incident_id=:id"), {"id": incident_id})
            ).mappings().first()
            if not row or row["status"] != "OPEN":
                return
            await session.execute(
                text("UPDATE incidents SET status='INVESTIGATING' WHERE incident_id=:id"), {"id": incident_id}
            )
            await add_event(session, incident_id, "INVESTIGATION_STARTED")
            await session.commit()
            result = await investigate(session, dict(row))
            await add_event(session, incident_id, "EVIDENCE_COLLECTED")
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
            await add_event(session, incident_id, "APPROVAL_REQUESTED", {"plan_id": pid})
            meta = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"] or "{}")
            meta["investigation"] = result
            meta["remediation_plan_id"] = pid
            await session.execute(
                text("UPDATE incidents SET status='MITIGATING', metadata=:m WHERE incident_id=:id"),
                {"m": json.dumps(meta, default=str), "id": incident_id},
            )
            await session.commit()
    except Exception:
        return


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with SessionLocal() as session:
        await seed(session)
    task = asyncio.create_task(detection_loop())
    yield
    task.cancel()


app = FastAPI(
    title="APIR Control Plane",
    description="Autonomous Production Incident Resolver API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://frontend:3000",
        "http://127.0.0.1:3000",
        "https://apir-frontend-production.up.railway.app",
    ],
    allow_origin_regex=r"https://.*\.up\.railway\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_hits: dict[str, list[float]] = {}


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    import time

    ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _hits.setdefault(ip, [])
    _hits[ip] = [t for t in window if now - t < 60]
    limit = 20 if request.url.path.endswith("/login") else 180
    if len(_hits[ip]) >= limit:
        logger.warning(json.dumps({
            "event": "rate_limit_exceeded",
            "ip": ip,
            "path": request.url.path,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))
        return JSONResponse({"error": "rate limited"}, status_code=429)
    _hits[ip].append(now)
    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "apir-backend", "timestamp": datetime.now(timezone.utc).isoformat()}


app.include_router(router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )

