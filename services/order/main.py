from __future__ import annotations

import os
import time
import uuid

import asyncpg
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field

from apir_shared.http_client import CircuitBreaker, request_with_retry
from apir_shared.middleware import create_service_app

SERVICE = "order-service"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://apir:apir@localhost:5432/apir")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8083")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8082")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL", "http://localhost:8084")

app, metrics, logger, failures = create_service_app(SERVICE, REDIS_URL)
pool: asyncpg.Pool | None = None
inv_breaker = CircuitBreaker()
pay_breaker = CircuitBreaker()
notif_breaker = CircuitBreaker()
client = httpx.AsyncClient()


class OrderItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=100)


class CreateOrder(BaseModel):
    user_id: str
    items: list[OrderItem]
    payment_method: str = "card"


@app.on_event("startup")
async def startup() -> None:
    global pool
    dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)


@app.on_event("shutdown")
async def shutdown() -> None:
    if pool:
        await pool.close()
    await client.aclose()


async def db_fetch(query: str, *args):
    assert pool
    t0 = time.perf_counter()
    if failures:
        delay = await failures.db_delay_seconds()
        if delay:
            import asyncio

            await asyncio.sleep(delay)
    result = await pool.fetch(query, *args)
    metrics.database_latency.labels(SERVICE, "query").observe(time.perf_counter() - t0)
    return result


async def db_execute(query: str, *args):
    assert pool
    t0 = time.perf_counter()
    if failures:
        delay = await failures.db_delay_seconds()
        if delay:
            import asyncio

            await asyncio.sleep(delay)
    result = await pool.execute(query, *args)
    metrics.database_latency.labels(SERVICE, "exec").observe(time.perf_counter() - t0)
    return result


@app.post("/orders")
async def create_order(body: CreateOrder):
    if not body.items:
        raise HTTPException(400, "items required")
    order_id = str(uuid.uuid4())
    await db_execute(
        """
        INSERT INTO orders (id, user_id, status, total_cents, payment_method)
        VALUES ($1, $2, 'pending', 0, $3)
        """,
        order_id,
        body.user_id,
        body.payment_method,
    )
    try:
        reserved = await request_with_retry(
            client,
            "POST",
            f"{INVENTORY_URL}/reserve",
            retries=1,
            timeout=5.0,
            breaker=inv_breaker,
            idempotent=False,
            json={"order_id": order_id, "items": [i.model_dump() for i in body.items]},
        )
        reserved_data = reserved.json()
        total = reserved_data.get("total_cents", 0)
        payment = await request_with_retry(
            client,
            "POST",
            f"{PAYMENT_URL}/payments",
            retries=1,
            timeout=6.0,
            breaker=pay_breaker,
            idempotent=False,
            json={
                "order_id": order_id,
                "amount_cents": total,
                "method": body.payment_method,
            },
        )
        payment_data = payment.json()
        try:
            await request_with_retry(
                client,
                "POST",
                f"{NOTIFICATION_URL}/notify",
                retries=1,
                timeout=3.0,
                breaker=notif_breaker,
                json={"order_id": order_id, "user_id": body.user_id, "event": "order_placed"},
            )
        except Exception:
            logger.log("WARNING", "notification failed", metadata={"order_id": order_id})
        await db_execute(
            "UPDATE orders SET status='confirmed', total_cents=$2 WHERE id=$1",
            order_id,
            total,
        )
        for item in body.items:
            await db_execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, price_cents)
                VALUES ($1, $2, $3, $4)
                """,
                order_id,
                item.product_id,
                item.quantity,
                0,
            )
        return {
            "order_id": order_id,
            "status": "confirmed",
            "total_cents": total,
            "payment": payment_data,
        }
    except Exception as exc:
        await db_execute("UPDATE orders SET status='failed' WHERE id=$1", order_id)
        logger.log("ERROR", "order flow failed", metadata={"order_id": order_id, "error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    rows = await db_fetch("SELECT * FROM orders WHERE id=$1", order_id)
    if not rows:
        raise HTTPException(404, "not found")
    return dict(rows[0])
