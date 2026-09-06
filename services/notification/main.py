from __future__ import annotations

import os
import time
import uuid

import asyncpg
from pydantic import BaseModel

from apir_shared.middleware import create_service_app

SERVICE = "notification-service"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://apir:apir@localhost:5432/apir")

app, metrics, logger, failures = create_service_app(SERVICE, REDIS_URL)
pool: asyncpg.Pool | None = None


class NotifyRequest(BaseModel):
    order_id: str
    user_id: str
    event: str = "order_placed"


@app.on_event("startup")
async def startup() -> None:
    global pool
    dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)


@app.on_event("shutdown")
async def shutdown() -> None:
    if pool:
        await pool.close()


@app.post("/notify")
async def notify(body: NotifyRequest):
    assert pool
    t0 = time.perf_counter()
    nid = str(uuid.uuid4())
    await pool.execute(
        """
        INSERT INTO notifications (id, order_id, channel, status)
        VALUES ($1, $2, 'email', 'sent')
        """,
        nid,
        body.order_id,
    )
    metrics.database_latency.labels(SERVICE, "insert").observe(time.perf_counter() - t0)
    logger.log("INFO", "notification sent", metadata={"order_id": body.order_id, "event": body.event})
    return {"notification_id": nid, "status": "sent"}
