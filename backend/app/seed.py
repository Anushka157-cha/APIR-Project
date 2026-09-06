from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.config import settings
from app.rag import ingest_knowledge


async def seed(session: AsyncSession) -> None:
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
