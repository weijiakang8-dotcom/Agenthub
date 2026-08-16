from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database import async_session_factory
from app.models import Document
from app.rag.embedder import cosine, embed_text


async def retrieve_documents(
    query: str,
    organization_id: str | uuid.UUID | None,
    top_k: int = 3,
) -> list[dict]:
    if not query:
        return []

    query_vec = await embed_text(query)
    async with async_session_factory() as session:
        stmt = select(Document)
        if organization_id is not None:
            stmt = stmt.where(
                Document.organization_id == uuid.UUID(str(organization_id))
            )
        documents = (await session.execute(stmt)).scalars().all()

    scored = []
    keywords = query.lower().split()
    for doc in documents:
        vector_score = cosine(query_vec, doc.embedding or [])
        keyword_score = sum(1 for k in keywords if k in doc.content.lower())
        score = vector_score + keyword_score * 0.2
        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"name": doc.name, "content": doc.content} for _, doc in scored[:top_k]]
