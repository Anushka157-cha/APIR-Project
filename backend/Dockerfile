FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    fastapi==0.115.6 uvicorn==0.34.0 httpx==0.28.1 redis==5.2.1 asyncpg==0.30.0 \
    sqlalchemy==2.0.36 pydantic==2.10.4 pydantic-settings==2.7.0 \
    "python-jose[cryptography]==3.3.0" "passlib[bcrypt]==1.7.4" bcrypt==4.2.1 \
    prometheus-client==0.21.1 docker==7.1.0 \
    opentelemetry-api==1.29.0 opentelemetry-sdk==1.29.0 \
    opentelemetry-instrumentation-fastapi==0.50b0 \
    opentelemetry-exporter-otlp-proto-http==1.29.0
COPY shared /shared
RUN pip install --no-cache-dir /shared
COPY backend /app
COPY knowledge /knowledge
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
ENV KNOWLEDGE_DIR=/knowledge
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
