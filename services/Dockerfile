FROM python:3.12-slim
WORKDIR /app
ARG SERVICE_NAME
ARG PORT=8080
ENV PORT=${PORT}
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir \
    fastapi==0.115.6 uvicorn==0.34.0 httpx==0.28.1 redis==5.2.1 asyncpg==0.30.0 \
    prometheus-client==0.21.1 pydantic==2.10.4 pydantic-settings==2.7.0 \
    opentelemetry-api==1.29.0 opentelemetry-sdk==1.29.0 \
    opentelemetry-instrumentation-fastapi==0.50b0 \
    opentelemetry-exporter-otlp-proto-http==1.29.0 \
    opentelemetry-instrumentation-httpx==0.50b0
COPY shared /shared
RUN pip install --no-cache-dir /shared
COPY services/${SERVICE_NAME} /app
EXPOSE ${PORT}
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
