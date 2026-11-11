"""向量检索：SQLite 存向量 + numpy 余弦暴力检索。

为什么不用 Chroma：零外部依赖、单机千级~十万级 chunk 性能足够（10 万块 × 1024 维
一次检索约几十毫秒），并且可以随时替换成 Milvus / pgvector —— 检索接口只有 search()。
"""
from __future__ import annotations

import threading

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Chunk
from .embeddings import from_blob

_lock = threading.Lock()
_cache: dict[int, tuple[int, np.ndarray, list[int]]] = {}


def invalidate(kb_id: int) -> None:
    with _lock:
        _cache.pop(kb_id, None)


def _matrix(db: Session, kb_id: int) -> tuple[np.ndarray, list[int]]:
    count = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.kb_id == kb_id)) or 0
    with _lock:
        cached = _cache.get(kb_id)
        if cached and cached[0] == count:
            return cached[1], cached[2]

    rows = db.execute(select(Chunk.id, Chunk.vector).where(Chunk.kb_id == kb_id)).all()
    ids = [r[0] for r in rows]
    if rows:
        mat = np.vstack([from_blob(r[1]) for r in rows])
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        mat = mat / norms
    else:
        mat = np.zeros((0, 1), dtype=np.float32)

    with _lock:
        _cache[kb_id] = (count, mat, ids)
    return mat, ids


def search(db: Session, kb_id: int, query_vec: list[float], top_k: int = 10) -> list[dict]:
    mat, ids = _matrix(db, kb_id)
    if mat.shape[0] == 0:
        return []
    q = np.asarray(query_vec, dtype=np.float32)
    if q.shape[0] != mat.shape[1]:
        raise ValueError(
            f"向量维度不一致：查询 {q.shape[0]}，库中 {mat.shape[1]}。换 embedding 模型后需要重建索引。"
        )
    q = q / (np.linalg.norm(q) or 1.0)
    scores = mat @ q
    order = np.argsort(-scores)[:top_k]
    return [{"chunk_id": ids[i], "score": float(scores[i])} for i in order]


def similarities(db: Session, kb_id: int, query_vec: list[float], chunk_ids: list[int]) -> dict[int, float]:
    """给指定 chunk 计算与查询的余弦相似度（复用已缓存的矩阵）。"""
    mat, ids = _matrix(db, kb_id)
    if mat.shape[0] == 0:
        return {cid: 0.0 for cid in chunk_ids}
    q = np.asarray(query_vec, dtype=np.float32)
    if q.shape[0] != mat.shape[1]:
        raise ValueError(
            f"向量维度不一致：查询 {q.shape[0]}，库中 {mat.shape[1]}。换 embedding 模型后需要重建索引。"
        )
    q = q / (np.linalg.norm(q) or 1.0)
    pos = {cid: i for i, cid in enumerate(ids)}
    out: dict[int, float] = {}
    for cid in chunk_ids:
        i = pos.get(cid)
        out[cid] = float(mat[i] @ q) if i is not None else 0.0
    return out
