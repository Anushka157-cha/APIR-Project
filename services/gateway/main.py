from __future__ import annotations

import os
import uuid

import httpx
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field

from apir_shared.http_client import CircuitBreaker, request_with_retry
from apir_shared.middleware import create_service_app

SERVICE = "gateway"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ORDER_URL = os.getenv("ORDER_URL", "http://localhost:8081")

app, metrics, logger, failures = create_service_app(SERVICE, REDIS_URL)
breaker = CircuitBreaker()
client = httpx.AsyncClient()


class OrderItem(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=100)


class CreateOrder(BaseModel):
    user_id: str
    items: list[OrderItem]
    payment_method: str = "card"


@app.post("/orders")
async def create_order(
    body: CreateOrder,
    x_request_id: str | None = Header(default=None),
):
    request_id = x_request_id or str(uuid.uuid4())
    try:
        response = await request_with_retry(
            client,
            "POST",
            f"{ORDER_URL}/orders",
            retries=2,
            timeout=8.0,
            breaker=breaker,
            idempotent=False,
            json=body.model_dump(),
            headers={"x-request-id": request_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"order-service unavailable: {exc}") from exc
    return response.json()


@app.get("/")
async def root():
    return {"service": SERVICE, "routes": ["/orders"]}
