from __future__ import annotations

import asyncio
import os
import time
import uuid

import asyncpg
from fastapi import HTTPException
from pydantic import BaseModel, Field

from apir_shared.middleware import create_service_app

SERVICE = "inventory-service"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://apir:apir@localhost:5432/apir")

app, metrics, logger, failures = create_service_app(SERVICE, REDIS_URL)
pool: asyncpg.Pool | None = None


class Item(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


class ReserveRequest(BaseModel):
    order_id: str
    items: list[Item]


@app.on_event("startup")
async def startup() -> None:
    global pool
    dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)


@app.on_event("shutdown")
async def shutdown() -> None:
    if pool:
        await pool.close()


async def timed_conn():
    assert pool
    t0 = time.perf_counter()
    if failures:
        delay = await failures.db_delay_seconds()
        if delay:
            await asyncio.sleep(delay)
    conn = await pool.acquire()
    metrics.database_latency.labels(SERVICE, "acquire").observe(time.perf_counter() - t0)
    return conn


@app.get("/products")
async def products():
    conn = await timed_conn()
    try:
        rows = await conn.fetch(
            "SELECT p.id, p.sku, p.name, p.price_cents, i.quantity FROM products p JOIN inventory i ON i.product_id=p.id"
        )
        return [dict(r) for r in rows]
    finally:
        await pool.release(conn)


@app.post("/reserve")
async def reserve(body: ReserveRequest):
    conn = await timed_conn()
    try:
        async with conn.transaction():
            total = 0
            for item in body.items:
                row = await conn.fetchrow(
                    """
                    SELECT i.quantity, p.price_cents
                    FROM inventory i JOIN products p ON p.id=i.product_id
                    WHERE i.product_id=$1 FOR UPDATE
                    """,
                    item.product_id,
                )
                if not row:
                    raise HTTPException(404, f"unknown product {item.product_id}")
                if row["quantity"] < item.quantity:
                    raise HTTPException(409, f"insufficient stock for {item.product_id}")
                await conn.execute(
                    "UPDATE inventory SET quantity=quantity-$1, updated_at=NOW() WHERE product_id=$2",
                    item.quantity,
                    item.product_id,
                )
                total += row["price_cents"] * item.quantity
            return {"order_id": body.order_id, "reserved": True, "total_cents": total}
    finally:
        await pool.release(conn)
