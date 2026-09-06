from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST


class MetricsRegistry:
    def __init__(self, service: str, registry: CollectorRegistry | None = None) -> None:
        self.service = service
        self.registry = registry or CollectorRegistry()
        labels = ("service", "method", "endpoint", "status")
        self.request_count = Counter(
            "request_count",
            "Total HTTP requests",
            labels,
            registry=self.registry,
        )
        self.error_count = Counter(
            "error_count",
            "Total HTTP errors (status >= 400)",
            ("service", "method", "endpoint", "status_class"),
            registry=self.registry,
        )
        self.request_latency = Histogram(
            "request_latency_seconds",
            "Request latency in seconds",
            ("service", "method", "endpoint"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
        self.active_requests = Gauge(
            "active_requests",
            "In-flight HTTP requests",
            ("service",),
            registry=self.registry,
        )
        self.service_health = Gauge(
            "service_health",
            "1 if healthy else 0",
            ("service",),
            registry=self.registry,
        )
        self.database_latency = Histogram(
            "database_latency_seconds",
            "Database call latency",
            ("service", "operation"),
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
            registry=self.registry,
        )
        self.service_health.labels(service=service).set(1)

    def observe_request(
        self,
        method: str,
        endpoint: str,
        status: int,
        latency_seconds: float,
    ) -> None:
        status_str = str(status)
        self.request_count.labels(self.service, method, endpoint, status_str).inc()
        self.request_latency.labels(self.service, method, endpoint).observe(latency_seconds)
        if status >= 400:
            status_class = "5xx" if status >= 500 else "4xx"
            self.error_count.labels(self.service, method, endpoint, status_class).inc()

    def set_health(self, healthy: bool) -> None:
        self.service_health.labels(service=self.service).set(1 if healthy else 0)

    def dump(self) -> tuple[bytes, str]:
        return generate_latest(self.registry), CONTENT_TYPE_LATEST
