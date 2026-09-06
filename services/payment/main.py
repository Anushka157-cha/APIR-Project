from __future__ import annotations

import asyncio
import os
import time
import uuid

import asyncpg
from pydantic import BaseModel, Field

from apir_shared.middleware import create_service_app

SERVICE = "payment-service"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://apir:apir@localhost:5432/apir")

app, metrics, logger, failures = create_service_app(SERVICE, REDIS_URL)
pool: asyncpg.Pool | None = None


class PaymentRequest(BaseModel):
    order_id: str
    amount_cents: int = Field(ge=0)
    method: str = "card"


@app.on_event("startup")
async def startup() -> None:
    global pool
    dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=8)


@app.on_event("shutdown")
async def shutdown() -> None:
    if pool:
        await pool.close()


@app.post("/payments")
async def pay(body: PaymentRequest):
    assert pool
    t0 = time.perf_counter()
    if failures:
        delay = await failures.db_delay_seconds()
        cfg = await failures.get_config()
        if cfg.get("pool_exhaust") == "1":
            logger.log(
                "ERROR",
                "database connection pool exhaustion",
                endpoint="/payments",
                metadata={"utilization": 0.98, "order_id": body.order_id},
            )
            await asyncio.sleep(float(cfg.get("pool_wait_s") or 1.2))
        if delay:
            await asyncio.sleep(delay)
    payment_id = str(uuid.uuid4())
    await pool.execute(
        """
        INSERT INTO payments (id, order_id, amount_cents, method, status)
        VALUES ($1, $2, $3, $4, 'captured')
        """,
        payment_id,
        body.order_id,
        body.amount_cents,
        body.method,
    )
    metrics.database_latency.labels(SERVICE, "insert").observe(time.perf_counter() - t0)
    await asyncio.sleep(0.02)
    return {
        "payment_id": payment_id,
        "order_id": body.order_id,
        "status": "captured",
        "amount_cents": body.amount_cents,
    }
