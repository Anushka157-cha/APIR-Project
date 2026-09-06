from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.stats import cosine, hashed_embedding


CHUNK_SIZE = 600


def chunk_text(text_value: str) -> list[str]:
    parts = []
    buf = []
    count = 0
    for line in text_value.splitlines():
        buf.append(line)
        count += len(line)
        if count >= CHUNK_SIZE:
            parts.append("\n".join(buf))
            buf, count = [], 0
    if buf:
        parts.append("\n".join(buf))
    return parts or [text_value]


async def ingest_knowledge(session: AsyncSession, *, reindex: bool = False) -> int:
    root = Path(settings.knowledge_dir)
    if not root.exists():
        root = Path(__file__).resolve().parents[2] / "knowledge"
    existing = await session.execute(text("SELECT COUNT(*) FROM document_chunks"))
    n = int(existing.scalar() or 0)
    if n > 0 and not reindex:
        return n
    if reindex:
        await session.execute(text("DELETE FROM document_chunks"))
    count = 0
    for path in root.rglob("*"):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        source = path.parent.name
        document = path.name
        raw = path.read_text(encoding="utf-8")
        for chunk in chunk_text(raw):
            checksum = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            emb = hashed_embedding(chunk)
            await session.execute(
                text(
                    """
                    INSERT INTO document_chunks (source, document, chunk, embedding, metadata, checksum)
                    VALUES (:source, :document, :chunk, :embedding, :metadata, :checksum)
                    ON CONFLICT (checksum) DO NOTHING
                    """
                ),
                {
                    "source": source,
                    "document": document,
                    "chunk": chunk,
                    "embedding": json.dumps(emb),
                    "metadata": json.dumps({"path": str(path), "checksum": checksum, "embedding_type": "hashed-local"}),
                    "checksum": checksum,
                },
            )
            count += 1
    await session.commit()
    return count


async def search(
    session: AsyncSession,
    query: str,
    *,
    source: str | None = None,
    limit: int = 5,
) -> list[dict]:
    qvec = hashed_embedding(query)
    sql = "SELECT id, source, document, chunk, embedding, metadata FROM document_chunks"
    params: dict = {}
    if source:
        sql += " WHERE source = :source"
        params["source"] = source
    rows = (await session.execute(text(sql), params)).mappings().all()
    scored = []
    for row in rows:
        emb = row["embedding"]
        if isinstance(emb, str):
            emb = json.loads(emb)
        score = cosine(qvec, list(emb))
        scored.append(
            {
                "source": row["source"],
                "document": row["document"],
                "chunk": row["chunk"],
                "relevance_score": round(float(score), 4),
                "metadata": row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"] or "{}"),
            }
        )
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:limit]
