from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.config import settings
from app.rag import ingest_knowledge

SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('ADMIN', 'SRE', 'VIEWER')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        sku TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        price_cents INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS inventory (
        product_id TEXT PRIMARY KEY REFERENCES products(id),
        quantity INTEGER NOT NULL CHECK (quantity >= 0),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id),
        status TEXT NOT NULL,
        total_cents INTEGER NOT NULL DEFAULT 0,
        payment_method TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)",
    """CREATE TABLE IF NOT EXISTS order_items (
        id SERIAL PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES orders(id),
        product_id TEXT NOT NULL REFERENCES products(id),
        quantity INTEGER NOT NULL,
        price_cents INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id)",
    """CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES orders(id),
        amount_cents INTEGER NOT NULL,
        method TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_id)",
    """CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL REFERENCES orders(id),
        channel TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS deployments (
        id SERIAL PRIMARY KEY,
        service TEXT NOT NULL,
        version TEXT NOT NULL,
        deployed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        notes TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS incidents (
        incident_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        severity TEXT NOT NULL,
        status TEXT NOT NULL,
        service TEXT NOT NULL,
        incident_type TEXT NOT NULL,
        detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at TIMESTAMPTZ,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    )""",
    "CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status)",
    "CREATE INDEX IF NOT EXISTS idx_incidents_service ON incidents(service)",
    "CREATE INDEX IF NOT EXISTS idx_incidents_detected ON incidents(detected_at)",
    """CREATE TABLE IF NOT EXISTS incident_events (
        id SERIAL PRIMARY KEY,
        incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
        event_type TEXT NOT NULL,
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_incident_events_incident ON incident_events(incident_id)",
    """CREATE TABLE IF NOT EXISTS remediation_plans (
        id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
        action_id TEXT NOT NULL,
        target TEXT NOT NULL,
        reason TEXT,
        risk TEXT NOT NULL,
        expected_effect TEXT,
        rollback_plan TEXT,
        status TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS remediation_executions (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL REFERENCES remediation_plans(id),
        approved_by TEXT,
        result TEXT,
        details JSONB NOT NULL DEFAULT '{}'::jsonb,
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at TIMESTAMPTZ
    )""",
    """CREATE TABLE IF NOT EXISTS audit_logs (
        id SERIAL PRIMARY KEY,
        username TEXT,
        action TEXT NOT NULL,
        target TEXT,
        incident_id TEXT,
        approval TEXT,
        result TEXT,
        reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at)",
    """CREATE TABLE IF NOT EXISTS failure_events (
        id SERIAL PRIMARY KEY,
        scenario TEXT NOT NULL,
        target TEXT,
        action TEXT NOT NULL,
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        stopped_at TIMESTAMPTZ,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    )""",
    """CREATE TABLE IF NOT EXISTS evaluation_runs (
        id TEXT PRIMARY KEY,
        scenario TEXT NOT NULL,
        incident_id TEXT,
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at TIMESTAMPTZ,
        detection_ms INTEGER,
        investigation_ms INTEGER,
        resolution_ms INTEGER,
        rca_correct BOOLEAN,
        remediation_success BOOLEAN,
        false_positive BOOLEAN,
        metrics JSONB NOT NULL DEFAULT '{}'::jsonb
    )""",
    """CREATE TABLE IF NOT EXISTS document_chunks (
        id SERIAL PRIMARY KEY,
        source TEXT NOT NULL,
        document TEXT NOT NULL,
        chunk TEXT NOT NULL,
        embedding JSONB,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
    )""",
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS checksum TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_document_chunks_checksum ON document_chunks(checksum)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_source ON document_chunks(source)",
    "CREATE INDEX IF NOT EXISTS idx_remediation_plans_incident ON remediation_plans(incident_id)",
    "CREATE INDEX IF NOT EXISTS idx_evaluation_runs_incident ON evaluation_runs(incident_id)",
]


async def seed(session: AsyncSession) -> None:
    for stmt in SCHEMA_STATEMENTS:
        try:
            await session.execute(text(stmt))
        except Exception:
            pass
    await session.commit()

    await session.execute(
        text(
            """
            INSERT INTO users (id, username, email, password_hash, role)
            VALUES
            ('user123', 'shopper', 'shopper@example.com', :p, 'VIEWER'),
            ('admin', 'admin', 'admin@apir.local', :admin, 'ADMIN'),
            ('sre', 'sre', 'sre@apir.local', :sre, 'SRE'),
            ('viewer', 'viewer', 'viewer@apir.local', :viewer, 'VIEWER')
            ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role
            """
        ),
        {
            "p": hash_password("shopper123"),
            "admin": hash_password(settings.demo_admin_password),
            "sre": hash_password(settings.demo_sre_password),
            "viewer": hash_password(settings.demo_viewer_password),
        },
    )
    await session.commit()
    await ingest_knowledge(session)

