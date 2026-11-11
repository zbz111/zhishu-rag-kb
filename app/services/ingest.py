"""索引流水线：解析 → 切分 → 向量化 → 入库。在后台线程执行，失败可重试。"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime

from sqlalchemy import delete, select

from ..config import settings
from ..db import SessionLocal
from ..models import Chunk, Document
from . import parser, splitter, vector_store
from .embeddings import embed_texts, to_blob

logger = logging.getLogger(__name__)


def run_ingest(doc_id: int, force: bool = False) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if doc is None:
            return

        doc.status = "parsing"
        doc.error = ""
        db.commit()

        blocks = parser.parse_file(doc.stored_path)

        pairs: list[tuple[int, int, str]] = []  # (page, index, text)
        for block in blocks:
            for idx, chunk in enumerate(
                splitter.split_text(block["text"], settings.chunk_size, settings.chunk_overlap)
            ):
                pairs.append((int(block.get("page", 1)), idx, chunk))

        if not pairs:
            raise ValueError("切分后没有任何内容")

        doc.status = "indexing"
        db.commit()

        if force:
            _delete_chunks(db, doc_id)
            db.commit()

        texts = [p[2] for p in pairs]
        vectors: list[list[float]] = []
        # 真正的批次上限在 embeddings 内部按服务商控制（阿里云 10 条/次），这里只做进度切块
        batch = max(10, int(settings.embed_batch_size))
        for i in range(0, len(texts), batch):
            vectors.extend(embed_texts(texts[i : i + batch]))

        for (page, idx, text), vec in zip(pairs, vectors, strict=True):
            db.add(
                Chunk(
                    document_id=doc_id,
                    kb_id=doc.kb_id,
                    page=page,
                    chunk_index=idx,
                    text=text,
                    vector=to_blob(vec),
                    dim=len(vec),
                )
            )

        doc.chunk_count = len(pairs)
        doc.status = "ready"
        doc.indexed_at = datetime.now()
        db.commit()
        vector_store.invalidate(doc.kb_id)
        logger.info("ingest done doc=%s chunks=%s", doc_id, len(pairs))

    except Exception as exc:  # noqa: BLE001
        logger.error("ingest failed doc=%s: %s", doc_id, exc)
        logger.debug(traceback.format_exc())
        doc = db.get(Document, doc_id)
        if doc is not None:
            doc.status = "failed"
            doc.error = str(exc)[:1000]
            db.commit()
    finally:
        db.close()


def _delete_chunks(db, doc_id: int) -> None:
    db.execute(delete(Chunk).where(Chunk.document_id == doc_id))


def delete_document_chunks(doc_id: int) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        kb_id = doc.kb_id if doc else None
        _delete_chunks(db, doc_id)
        db.commit()
        if kb_id:
            vector_store.invalidate(kb_id)
    finally:
        db.close()


def corpus_for_kb(db, kb_id: int) -> list[Chunk]:
    return list(db.scalars(select(Chunk).where(Chunk.kb_id == kb_id)).all())
