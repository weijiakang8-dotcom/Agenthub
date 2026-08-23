from __future__ import annotations

import hashlib

import pytest

from app.kernel.artifact.model import Artifact
from app.kernel.artifact.store import ArtifactStore
from app.kernel.evidence.model import EvidenceLevel


def _make(content: bytes, artifact_id: str = "a1") -> Artifact:
    return Artifact.create(
        artifact_id=artifact_id,
        artifact_type="text/plain",
        content=content,
        evidence_level=EvidenceLevel.L2_SUPPORTED,
        producer="test",
    )


def test_artifact_content_addressing():
    first = _make(b"hello")
    same_content = _make(b"hello", artifact_id="a2")
    different = _make(b"world", artifact_id="a3")

    assert first.content_hash == hashlib.sha256(b"hello").hexdigest()
    assert first.content_hash == same_content.content_hash
    assert first.content_hash != different.content_hash


def test_artifact_store_put_get_and_ref():
    store = ArtifactStore()
    artifact = _make(b"payload")

    ref = store.put(artifact)

    assert store.has(artifact.artifact_id) is True
    assert store.get(artifact.artifact_id) is artifact
    assert ref.artifact_id == artifact.artifact_id
    assert ref.content_hash == artifact.content_hash
    assert store.get_by_content_hash(artifact.content_hash) is artifact


def test_artifact_store_rejects_content_hash_mismatch():
    store = ArtifactStore()
    tampered = Artifact(
        artifact_id="tampered",
        artifact_type="text/plain",
        content=b"real-payload",
        content_hash=hashlib.sha256(b"other-payload").hexdigest(),
        evidence_level=EvidenceLevel.L2_SUPPORTED,
        producer="test",
    )

    with pytest.raises(ValueError):
        store.put(tampered)
