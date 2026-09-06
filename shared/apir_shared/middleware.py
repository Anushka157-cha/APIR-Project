from __future__ import annotations

import json
import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from apir_shared.failures import (
    DatabaseDisabled,
    FailureController,
    InjectedHttpError,
    ServiceCrashed,
)
from apir_shared.logging import JsonLogger
from apir_shared.metrics import MetricsRegistry
from apir_shared.tracing import current_trace_id, setup_tracing


class ObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        service: str,
        metrics: MetricsRegistry,
        logger: JsonLogger,
        failures: FailureController | None,
        log_sink: Callable[[dict], None] | None = None,
    ) -> None:
        super().__init__(app)
        self.service = service
        self.metrics = metrics
        self.logger = logger
        self.failures = failures
        self.log_sink = log_sink

    async def dispatch(self, request: Request, call_next):
        if request.url.path in {"/metrics", "/health", "/ready"}:
            return await call_next(request)

        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        status = 500
        try:
            if self.failures:
                await self.failures.apply_pre_request()
            response = await call_next(request)
            status = response.status_code
            latency_ms = (time.perf_counter() - start) * 1000
            response.headers["x-request-id"] = request_id
            trace_id = current_trace_id()
            if trace_id:
                response.headers["x-trace-id"] = trace_id
            self.metrics.observe_request(
                request.method, _route_label(request), status, latency_ms / 1000
            )
            entry = self.logger.log(
                "ERROR" if status >= 500 else "INFO",
                "request completed" if status < 400 else "request failed",
                request_id=request_id,
                trace_id=trace_id,
                endpoint=request.url.path,
                status_code=status,
                latency_ms=round(latency_ms, 2),
            )
            if self.log_sink:
                self.log_sink(entry)
            if self.failures:
                await self.failures.publish_log(entry)
            return response
        except ServiceCrashed:
            status = 503
            return await self._fail(request, request_id, start, status, "service crash injected")
        except InjectedHttpError as exc:
            status = exc.status_code
            return await self._fail(request, request_id, start, status, str(exc))
        except DatabaseDisabled as exc:
            status = 503
            return await self._fail(request, request_id, start, status, str(exc))
        except Exception as exc:
            status = 500
            return await self._fail(request, request_id, start, status, str(exc), exc=True)

    async def _fail(
        self,
        request: Request,
        request_id: str,
        start: float,
        status: int,
        message: str,
        exc: bool = False,
    ) -> JSONResponse:
        latency_ms = (time.perf_counter() - start) * 1000
        self.metrics.observe_request(
            request.method, _route_label(request), status, latency_ms / 1000
        )
        entry = self.logger.log(
            "ERROR",
            message,
            request_id=request_id,
            trace_id=current_trace_id(),
            endpoint=request.url.path,
            status_code=status,
            latency_ms=round(latency_ms, 2),
        )
        if self.log_sink:
            self.log_sink(entry)
        if self.failures:
            await self.failures.publish_log(entry)
        return JSONResponse(
            {"error": message, "request_id": request_id},
            status_code=status,
            headers={"x-request-id": request_id},
        )


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    if route and getattr(route, "path", None):
        return route.path
    return request.url.path


def create_service_app(
    service: str,
    redis_url: str,
    *,
    enable_failures: bool = True,
) -> tuple[FastAPI, MetricsRegistry, JsonLogger, FailureController | None]:
    app = FastAPI(title=service, version="0.1.0")
    metrics = MetricsRegistry(service)
    logger = JsonLogger(service)
    failures = FailureController(redis_url, service) if enable_failures else None
    log_buffer: list[dict] = []

    def sink(entry: dict) -> None:
        log_buffer.append(entry)
        if len(log_buffer) > 500:
            del log_buffer[: len(log_buffer) - 500]

    app.add_middleware(
        ObservabilityMiddleware,
        service=service,
        metrics=metrics,
        logger=logger,
        failures=failures,
        log_sink=sink,
    )
    setup_tracing(service, app)

    @app.get("/health")
    async def health():
        crashed = False
        if failures:
            cfg = await failures.get_config()
            crashed = cfg.get("crash") == "1"
        healthy = not crashed
        metrics.set_health(healthy)
        return {"status": "ok" if healthy else "down", "service": service}

    @app.get("/ready")
    async def ready():
        return {"ready": True, "service": service}

    @app.get("/metrics")
    async def prometheus_metrics():
        body, content_type = metrics.dump()
        return Response(content=body, media_type=content_type)

    @app.get("/internal/logs")
    async def recent_logs():
        return {"logs": log_buffer[-200:]}

    return app, metrics, logger, failures
