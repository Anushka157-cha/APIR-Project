from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import redis.asyncio as redis


class FailureController:
    """Reads allowlisted failure flags from Redis. Services never execute host commands."""

    def __init__(self, redis_url: str, service: str) -> None:
        self.service = service
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._cpu_task: asyncio.Task | None = None
        self._mem_blob: bytearray | None = None

    def _key(self) -> str:
        return f"failure:{self.service}"

    async def get_config(self) -> dict[str, Any]:
        raw = await self._redis.hgetall(self._key())
        return raw or {}

    async def apply_pre_request(self) -> dict[str, Any]:
        cfg = await self.get_config()
        if cfg.get("crash") == "1":
            raise ServiceCrashed(self.service)
        extra_ms = int(cfg.get("latency_ms") or 0)
        if extra_ms:
            jitter = int(cfg.get("latency_jitter_ms") or 0)
            delay = extra_ms + (random.randint(0, jitter) if jitter else 0)
            await asyncio.sleep(delay / 1000.0)
        error_rate = float(cfg.get("error_rate") or 0)
        if error_rate and random.random() < error_rate:
            raise InjectedHttpError(int(cfg.get("error_status") or 500), "injected 5xx error")
        if cfg.get("db_disabled") == "1":
            raise DatabaseDisabled("database unavailable (injected)")
        pool_exhaust = cfg.get("pool_exhaust") == "1"
        if pool_exhaust:
            await asyncio.sleep(float(cfg.get("pool_wait_s") or 1.5))
        self._maybe_start_stress(cfg)
        return cfg

    def _maybe_start_stress(self, cfg: dict[str, Any]) -> None:
        if cfg.get("cpu_stress") == "1" and self._cpu_task is None:
            self._cpu_task = asyncio.create_task(self._burn_cpu())
        if cfg.get("mem_stress") == "1" and self._mem_blob is None:
            mb = int(cfg.get("mem_mb") or 64)
            self._mem_blob = bytearray(mb * 1024 * 1024)
        if cfg.get("cpu_stress") != "1" and self._cpu_task:
            self._cpu_task.cancel()
            self._cpu_task = None
        if cfg.get("mem_stress") != "1":
            self._mem_blob = None

    async def _burn_cpu(self) -> None:
        while True:
            _ = sum(i * i for i in range(50000))
            await asyncio.sleep(0)

    async def db_delay_seconds(self) -> float:
        cfg = await self.get_config()
        return float(cfg.get("db_latency_ms") or 0) / 1000.0

    async def publish_log(self, entry: dict[str, Any]) -> None:
        key = f"logs:{self.service}"
        await self._redis.lpush(key, json.dumps(entry, default=str))
        await self._redis.ltrim(key, 0, 999)
        if entry.get("trace_id"):
            tkey = f"traces:{entry['trace_id']}"
            await self._redis.lpush(tkey, json.dumps(entry, default=str))
            await self._redis.ltrim(tkey, 0, 99)
            await self._redis.expire(tkey, 3600)


class ServiceCrashed(Exception):
    pass


class InjectedHttpError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class DatabaseDisabled(Exception):
    pass
