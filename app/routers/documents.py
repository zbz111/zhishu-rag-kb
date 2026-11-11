"""文档：上传、列表、删除、重建索引。解析与向量化在后台线程执行。"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import client_ip, get_current_user, require_kb_access
from ..models import Document, User
from ..schemas import DocumentOut
from ..services import ingest
from ..services.audit import audit

router = APIRouter(tags=["documents"])

ALLOWED = {".pdf", ".docx", ".xlsx", ".xlsm", ".md", ".txt", ".markdown"}


@router.get("/api/v1/kbs/{kb_id}/documents", response_model=list[DocumentOut])
def list_documents(
    kb_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_kb_access(kb_id, user, db, need="viewer")
    docs = db.scalars(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.id.desc())
    ).all()
    return [DocumentOut.model_validate(d) for d in docs]


@router.post(
    "/api/v1/kbs/{kb_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    kb_id: int,
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_kb_access(kb_id, user, db, need="editor")

    filename = Path(file.filename or "unnamed").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{suffix}")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="空文件")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {settings.max_upload_mb}MB")

    sha = hashlib.sha256(content).hexdigest()
    dup = db.scalar(
        select(Document).where(Document.kb_id == kb_id, Document.sha256 == sha, Document.status == "ready")
    )
    if dup:
        raise HTTPException(status_code=409, detail=f"该文档已存在：{dup.filename}")

    target_dir = settings.upload_dir / str(kb_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = target_dir / f"{uuid.uuid4().hex}{suffix}"
    stored.write_bytes(content)

    doc = Document(
        kb_id=kb_id,
        user_id=user.id,
        filename=filename,
        stored_path=str(stored),
        size=len(content),
        sha256=sha,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    audit(db, user.id, "doc_upload", filename, f"kb={kb_id} size={len(content)}", client_ip(request))
    background.add_task(ingest.run_ingest, doc.id)
    return DocumentOut.model_validate(doc)


@router.post("/api/v1/documents/{doc_id}/reindex", response_model=DocumentOut)
def reindex(
    doc_id: int,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    require_kb_access(doc.kb_id, user, db, need="editor")
    doc.status = "pending"
    doc.error = ""
    db.commit()
    background.add_task(ingest.run_ingest, doc.id, True)
    return DocumentOut.model_validate(doc)


@router.delete("/api/v1/documents/{doc_id}")
def delete_document(
    doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    require_kb_access(doc.kb_id, user, db, need="editor")
    ingest.delete_document_chunks(doc.id)
    Path(doc.stored_path).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    return {"ok": True}


@router.get("/api/v1/documents/{doc_id}/download")
def download(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    require_kb_access(doc.kb_id, user, db, need="viewer")
    path = Path(doc.stored_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="文件已丢失")
    return FileResponse(path, filename=doc.filename)
