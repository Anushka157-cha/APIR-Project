from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.dependency_graph import SERVICES


class PrometheusClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.prometheus_url).rstrip("/")

    async def query(self, expr: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(f"{self.base_url}/api/v1/query", params={"query": expr})
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                return []
        if data.get("status") != "success":
            return []
        return data.get("data", {}).get("result", [])

    async def query_range(self, expr: str, *, start: datetime, end: datetime, step_seconds: int = 30) -> list[dict[str, Any]]:
        """Return genuine Prometheus range samples; network failures produce no baseline."""
        params = {"query": expr, "start": start.timestamp(), "end": end.timestamp(), "step": step_seconds}
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                response = await client.get(f"{self.base_url}/api/v1/query_range", params=params)
                response.raise_for_status()
                data = response.json()
            except Exception:
                return []
        return data.get("data", {}).get("result", []) if data.get("status") == "success" else []

    async def baseline(self, service: str, *, minutes: int | None = None) -> dict[str, list[float]]:
        """Collect a time-window baseline from Prometheus, not synthetic defaults."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes or settings.baseline_window_minutes)
        expressions = {
            "p95_ms": f'histogram_quantile(0.95, sum by (le) (rate(request_latency_seconds_bucket{{service="{service}"}}[2m]))) * 1000',
            "error_rate": f'sum(rate(error_count{{service="{service}"}}[2m])) / clamp_min(sum(rate(request_count{{service="{service}"}}[2m])), 0.0001)',
            "rps": f'sum(rate(request_count{{service="{service}"}}[2m]))',
        }
        result: dict[str, list[float]] = {}
        for name, expression in expressions.items():
            series = await self.query_range(expression, start=start, end=end)
            values: list[float] = []
            for item in series:
                for pair in item.get("values", []):
                    try:
                        float_value = float(pair[1])
                        # Filter out NaN and infinite values
                        if float_value >= -1e308 and float_value <= 1e308:
                            values.append(float_value)
                    except (IndexError, TypeError, ValueError):
                        continue
            result[f"{service}:{name}"] = values
        return result

    async def snapshot(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {s: {} for s in SERVICES}
        mapping = {
            "p50_ms": 'histogram_quantile(0.5, sum by (le, service) (rate(request_latency_seconds_bucket[1m]))) * 1000',
            "p95_ms": 'histogram_quantile(0.95, sum by (le, service) (rate(request_latency_seconds_bucket[1m]))) * 1000',
            "p99_ms": 'histogram_quantile(0.99, sum by (le, service) (rate(request_latency_seconds_bucket[1m]))) * 1000',
            "rps": 'sum by (service) (rate(request_count[1m]))',
            "errors": 'sum by (service) (rate(error_count[1m]))',
            "health": 'max by (service) (service_health)',
            "active": 'max by (service) (active_requests)',
        }
        for key, expr in mapping.items():
            for series in await self.query(expr):
                svc = series.get("metric", {}).get("service")
                if svc not in out:
                    continue
                value = series.get("value", [None, "0"])[1]
                try:
                    float_value = float(value)
                    # Handle NaN and infinite values for JSON serialization
                    if not (float_value >= -1e308 and float_value <= 1e308):
                        float_value = 0.0
                    out[svc][key] = float_value
                except (TypeError, ValueError):
                    out[svc][key] = 0.0
        for svc, vals in out.items():
            rps = vals.get("rps") or 0
            errors = vals.get("errors") or 0
            vals["error_rate"] = (errors / rps) if rps > 0 else 0.0
        return out
