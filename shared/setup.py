from setuptools import setup, find_packages

setup(
    name="apir-shared",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.115.0",
        "starlette>=0.40.0",
        "prometheus-client>=0.21.0",
        "opentelemetry-api>=1.28.0",
        "opentelemetry-sdk>=1.28.0",
        "opentelemetry-instrumentation-fastapi>=0.49b0",
        "opentelemetry-exporter-otlp-proto-http>=1.28.0",
        "opentelemetry-instrumentation-httpx>=0.49b0",
        "httpx>=0.27.0",
        "redis>=5.2.0",
        "pydantic-settings>=2.6.0",
    ],
)
