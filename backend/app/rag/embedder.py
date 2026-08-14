from __future__ import annotations

import asyncio
import hashlib
import math
import re
from typing import Any

_model: Any = None


def _hash_embed(text: str, dims: int = 384) -> list[float]:
    vec = [0.0] * dims
    tokens = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text.lower())
    for i in range(len(tokens)):
        for n in (1, 2, 3):
            gram = " ".join(tokens[i : i + n])
            idx = int.from_bytes(hashlib.md5(gram.encode()).digest()[:4], "little") % dims
            vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _load_model() -> Any:
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
    except Exception:  # noqa: BLE001
        _model = False
    return _model


async def embed_text(text: str) -> list[float]:
    model = _load_model()
    if model is False:
        return _hash_embed(text)
    vectors = await asyncio.to_thread(model.encode, [text])
    vector = vectors[0].tolist() if hasattr(vectors[0], "tolist") else list(vectors[0])
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))
