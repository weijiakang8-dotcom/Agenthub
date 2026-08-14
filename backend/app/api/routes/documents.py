from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.models import Document
from app.rag.embedder import cosine, embed_text


router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentUpload(BaseModel):
    name: str
    content: str
    metadata: dict = {}


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


def _serialize(d: Document) -> dict:
    return {
        "id": str(d.id),
        "name": d.name,
        "content": d.content,
        "metadata": d.metadata_json,
        "created_at": d.created_at.isoformat(),
    }


@router.get("")
async def list_documents(session: SessionDep, user: CurrentUserDep) -> list[dict]:
    stmt = select(Document).order_by(Document.created_at.desc()).limit(200)
    if user.organization_id is not None:
        stmt = stmt.where(Document.organization_id == user.organization_id)
    result = await session.execute(stmt)
    return [_serialize(d) for d in result.scalars().all()]


@router.post("/upload", status_code=201)
async def upload_document(
    session: SessionDep,
    user: CurrentUserDep,
    file: UploadFile = File(...),
) -> dict:
    raw = await file.read()
    filename = file.filename or "document.txt"
    lower = filename.lower()

    if lower.endswith((".txt", ".md", ".markdown")):
        content = raw.decode("utf-8", errors="ignore")
    elif lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            from io import BytesIO

            reader = PdfReader(BytesIO(raw))
            content = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=f"PDF parsing failed: {exc}")
    else:
        raise HTTPException(status_code=422, detail="Unsupported file type")

    if not content.strip():
        raise HTTPException(status_code=422, detail="Document content is empty")

    embedding = await embed_text(content[:4000])
    document = Document(
        organization_id=user.organization_id,
        user_id=user.id,
        name=filename,
        content=content,
        metadata_json={"filename": filename, "content_type": file.content_type or ""},
        embedding=embedding,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return _serialize(document)


@router.post("", status_code=201)
async def create_document(
    payload: DocumentUpload, session: SessionDep, user: CurrentUserDep
) -> dict:
    embedding = await embed_text(payload.content[:4000])
    document = Document(
        organization_id=user.organization_id,
        user_id=user.id,
        name=payload.name,
        content=payload.content,
        metadata_json=payload.metadata,
        embedding=embedding,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return _serialize(document)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> None:
    document = await session.get(Document, document_id)
    if document is None or (
        user.organization_id is not None
        and document.organization_id != user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Document not found")
    await session.delete(document)
    await session.commit()


@router.post("/search")
async def search_documents(
    payload: SearchRequest, session: SessionDep, user: CurrentUserDep
) -> list[dict]:
    query_vec = await embed_text(payload.query)
    stmt = select(Document)
    if user.organization_id is not None:
        stmt = stmt.where(Document.organization_id == user.organization_id)
    documents = (await session.execute(stmt)).scalars().all()

    scored = []
    keywords = payload.query.lower().split()
    for doc in documents:
        vector_score = cosine(query_vec, doc.embedding or [])
        keyword_score = sum(1 for k in keywords if k in doc.content.lower())
        score = vector_score + keyword_score * 0.2
        scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [_serialize(doc) for _, doc in scored[: payload.top_k]]
