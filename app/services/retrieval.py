"""检索：向量 + BM25 混合，RRF 融合；可选 rerank。"""
from __future__ import annotations

import threading

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Chunk
from . import vector_store
from .embeddings import embed_query

_bm25_lock = threading.Lock()
_bm25_cache: dict[int, tuple[int, BM25Okapi, list[int]]] = {}
jieba.setLogLevel(20)


def invalidate(kb_id: int) -> None:
    with _bm25_lock:
        _bm25_cache.pop(kb_id, None)


def _tokenize(text: str) -> list[str]:
    return [w for w in jieba.cut_for_search(text) if w.strip()]


def _bm25(db: Session, kb_id: int) -> tuple[BM25Okapi | None, list[int]]:
    rows = db.execute(select(Chunk.id, Chunk.text).where(Chunk.kb_id == kb_id)).all()
    count = len(rows)
    with _bm25_lock:
        cached = _bm25_cache.get(kb_id)
        if cached and cached[0] == count:
            return cached[1], cached[2]

    if not rows:
        return None, []
    ids = [r[0] for r in rows]
    corpus = [_tokenize(r[1]) for r in rows]
    bm25 = BM25Okapi(corpus)
    with _bm25_lock:
        _bm25_cache[kb_id] = (count, bm25, ids)
    return bm25, ids


def _bm25_search(db: Session, kb_id: int, query: str, top_k: int) -> list[dict]:
    bm25, ids = _bm25(db, kb_id)
    if bm25 is None:
        return []
    scores = bm25.get_scores(_tokenize(query))
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [{"chunk_id": ids[i], "score": float(scores[i])} for i in order if scores[i] > 0]


def rrf_fuse(rankings: list[list[dict]], k: int = 60) -> list[dict]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item["chunk_id"]] = scores.get(item["chunk_id"], 0.0) + 1.0 / (k + rank)
    return sorted(
        ({"chunk_id": cid, "score": s} for cid, s in scores.items()),
        key=lambda x: x["score"],
        reverse=True,
    )


def retrieve(db: Session, kb_id: int, query: str, top_k: int | None = None) -> list[dict]:
    """混合检索 + 相似度过滤。

    返回的每一项都带两个分：
    - rrf：融合排名分（用于排序，数值很小，不适合展示）
    - sim：与查询的真实余弦相似度（用于展示与阈值过滤）
    """
    top_k = top_k or settings.top_k
    qvec = embed_query(query)
    vec_hits = vector_store.search(db, kb_id, qvec, settings.candidate_k)

    if settings.enable_hybrid:
        kw_hits = _bm25_search(db, kb_id, query, settings.candidate_k)
        fused = rrf_fuse([vec_hits, kw_hits])[:top_k]
    else:
        fused = vec_hits[:top_k]

    if not fused:
        return []

    sims = vector_store.similarities(db, kb_id, qvec, [h["chunk_id"] for h in fused])
    for item in fused:
        item["rrf"] = round(item["score"], 6)
        item["score"] = round(sims.get(item["chunk_id"], 0.0), 4)

    # 过滤：低于绝对阈值，或明显低于最高分的结果，都是噪声
    best = max(item["score"] for item in fused)
    floor = max(settings.min_similarity, best * settings.similarity_ratio)
    kept = [item for item in fused if item["score"] >= floor]
    if not kept:
        kept = [fused[0]]
    return kept


def hydrate(db: Session, hits: list[dict]) -> list[dict]:
    """把 chunk_id 补成完整信息（文本、文件名、页码）。"""
    if not hits:
        return []
    ids = [h["chunk_id"] for h in hits]
    rows = db.execute(
        select(Chunk.id, Chunk.document_id, Chunk.page, Chunk.text, Chunk.chunk_index).where(
            Chunk.id.in_(ids)
        )
    ).all()
    by_id = {r[0]: r for r in rows}
    from ..models import Document

    doc_ids = {r[1] for r in rows}
    docs = db.execute(select(Document.id, Document.filename).where(Document.id.in_(doc_ids))).all()
    names = {d[0]: d[1] for d in docs}

    out: list[dict] = []
    for h in hits:
        row = by_id.get(h["chunk_id"])
        if row is None:
            continue
        out.append(
            {
                "chunk_id": row[0],
                "document_id": row[1],
                "page": row[2],
                "text": row[3],
                "chunk_index": row[4],
                "filename": names.get(row[1], "未知文档"),
                "score": h.get("score", 0.0),
            }
        )
    return out
