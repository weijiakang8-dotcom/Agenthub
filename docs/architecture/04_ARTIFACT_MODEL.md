# Artifact Model

## What

Artifact 是任何 Capability 产生或消费的持久内容单元（文本、结构化数据、候选报告、派生结果）。Artifact 存放在 **Artifact Store**，State 只保存 `ArtifactRef`。

## Why

如果 State 直接保存完整 Artifact 内容：

1. 每次 Transition 都要复制大对象，破坏确定性和内存边界。
2. 无法做内容寻址、去重、校验和、溯源。
3. State 会退化为"消息列表"，重新回到旧架构的上下文污染。

分离之后，State 只是 Artifact 的 Projection，Artifact Store 才是内容的真相源。

## Formal Model

```python
from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field

from app.kernel.state import EvidenceLevel


class Artifact(BaseModel):
    id: str
    kind: str
    content: bytes
    content_type: str = "application/octet-stream"
    checksum: str
    evidence_level: EvidenceLevel
    created_by_capability: str
    task_ref: str | None = None
    metadata: dict = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        artifact_id: str,
        kind: str,
        content: bytes,
        content_type: str,
        evidence_level: EvidenceLevel,
        created_by_capability: str,
        task_ref: str | None = None,
        metadata: dict | None = None,
    ) -> "Artifact":
        return cls(
            id=artifact_id,
            kind=kind,
            content=content,
            content_type=content_type,
            checksum=hashlib.sha256(content).hexdigest(),
            evidence_level=evidence_level,
            created_by_capability=created_by_capability,
            task_ref=task_ref,
            metadata=metadata or {},
        )


class ArtifactRef(BaseModel):
    artifact_id: str
    checksum: str
    kind: str


class ArtifactStore(BaseModel):
    artifacts: dict[str, Artifact] = Field(default_factory=dict)

    def put(self, artifact: Artifact) -> ArtifactRef:
        self.artifacts[artifact.id] = artifact
        return ArtifactRef(
            artifact_id=artifact.id,
            checksum=artifact.checksum,
            kind=artifact.kind,
        )

    def get(self, ref: ArtifactRef) -> Artifact | None:
        artifact = self.artifacts.get(ref.artifact_id)
        if artifact is None or artifact.checksum != ref.checksum:
            return None
        return artifact
```

## Invariants

- `Artifact.checksum` 必须等于 `sha256(content)`。
- State 只能引用 `ArtifactRef`，不能内嵌 `Artifact.content`。
- `ArtifactStore.get(ref)` 必须校验 checksum，不匹配返回 None。
- 相同内容（同 checksum）可在内容寻址下复用，但不因此改变 evidence_level。

## Forbidden

- 把完整 Artifact 内容写进 `KnowledgeState` 或 `ObservedWorldState`。
- 用无 checksum 的引用访问 Artifact。
- 用 `artifact_id` 而不校验 checksum 判等。
- 让业务代码直接改 Artifact 的 `evidence_level`。

## Runtime Enforcement

- `TransitionEngine` 在 Projection 阶段只写入 `ArtifactRef`。
- `ArtifactStore` 是唯一能持有 `Artifact.content` 的组件。
- Phase 2 内存态下 `ArtifactStore` 就是一个进程内 dict；不引入文件系统。

## Failure Cases

1. checksum 不匹配 → `get` 返回 None。
2. State 中出现了 `content` 字段 → Schema 校验拒绝。
3. 两个不同 `artifact_id` 但相同内容 → 允许内容复用，但 provenance 必须各自保留。
4. 未校验 checksum 的引用 → Transition 后置校验失败。

## Test Requirements

- `TEST_03_STATE_PROJECTION`：State 与 Artifact Store 分离。
- checksum 校验成功/失败两个用例。
- 证明 State 序列化中不含 `Artifact.content`。

