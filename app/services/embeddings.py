"""向量化：支持 Ollama 本地模型、OpenAI 兼容接口、以及测试用的 hash 兜底。"""
from __future__ import annotations

import hashlib
from functools import lru_cache

import httpx
import numpy as np

from ..config import settings


class EmbeddingError(RuntimeError):
    pass


def _normalize(vec: list[float]) -> list[float]:
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm == 0:
        return arr.tolist()
    return (arr / norm).tolist()


def _ollama_embed(texts: list[str]) -> list[list[float]]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embed"
    with httpx.Client(timeout=120) as client:
        resp = client.post(url, json={"model": settings.ollama_embed_model, "input": texts})
        if resp.status_code == 404:
            raise EmbeddingError(
                f"Ollama 中没有模型 {settings.ollama_embed_model}，请先执行：ollama pull {settings.ollama_embed_model}"
            )
        resp.raise_for_status()
        data = resp.json()
    return data["embeddings"]


def _openai_embed(texts: list[str]) -> list[list[float]]:
    base = settings.openai_embed_base_url.rstrip("/")
    key = settings.openai_embed_api_key or settings.openai_api_key
    if not key:
        raise EmbeddingError("未配置 EMBED API Key")
    with httpx.Client(timeout=120) as client:
        try:
            resp = client.post(
                f"{base}/embeddings",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": settings.openai_embed_model, "input": texts},
            )
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"向量服务不可达：{exc}") from exc
        if resp.status_code >= 400:
            from .llm import friendly_status

            raise EmbeddingError(friendly_status(resp.status_code, resp.text))
        data = resp.json()
    return [item["embedding"] for item in data["data"]]


def _hash_embed(texts: list[str]) -> list[list[float]]:
    """离线兜底：确定性哈希向量。仅用于测试链路，语义效果差。"""
    dim = settings.vector_dim
    out: list[list[float]] = []
    for text in texts:
        vec = np.zeros(dim, dtype=np.float32)
        for token in set(text):
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16)
            vec[h % dim] += 1.0
        norm = float(np.linalg.norm(vec))
        out.append((vec / norm if norm else vec).tolist())
    return out


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化。

    注意：不同服务商的单次批大小不同——阿里云 text-embedding-v3 上限 10 条，
    超过会返回 400 InvalidParameter("batch size is invalid")。所以这里统一按
    settings.embed_batch_size 内部再分批，异常时自动对半拆批重试一次。
    """
    if not texts:
        return []

    provider = settings.llm_provider
    if provider == "hash":
        return [_normalize(v) for v in _hash_embed(texts)]

    batch = max(1, int(settings.embed_batch_size))
    vecs: list[list[float]] = []
    for i in range(0, len(texts), batch):
        part = texts[i : i + batch]
        try:
            vecs.extend(_embed_once(part))
        except EmbeddingError as exc:
            # 服务商批上限比配置更小：对半拆开重试，仍失败再抛出
            if len(part) <= 1:
                raise
            mid = len(part) // 2
            for sub in (part[:mid], part[mid:]):
                try:
                    vecs.extend(_embed_once(sub))
                except EmbeddingError:
                    vecs.extend([_embed_serial(t) for t in sub])
            _ = exc
    return [_normalize(v) for v in vecs]


def _embed_once(part: list[str]) -> list[list[float]]:
    provider = settings.llm_provider
    return _openai_embed(part) if provider == "openai" else _ollama_embed(part)


def _embed_serial(text: str) -> list[float]:
    """最后的兜底：逐条请求，保证单个坏块不拖垮整篇文档。"""
    return _embed_once([text])[0]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


@lru_cache(maxsize=1)
def probe_dim() -> int:
    """探测当前 embedding 模型维度，用于启动自检。"""
    try:
        return len(embed_query("维度探测"))
    except Exception:
        return 0


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def to_blob(vec: list[float]) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def rough_tokens(text: str) -> int:
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return max(1, int(cjk / 1.5 + (len(text) - cjk) / 4))
