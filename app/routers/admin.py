"""管理后台：用户管理、统计、审计日志、系统状态。"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import client_ip, require_admin
from ..models import AuditLog, Chunk, Conversation, Document, KnowledgeBase, Message, User
from ..schemas import AuditOut, StatsOut, UserCreate, UserOut
from ..security import hash_password
from ..services import llm
from ..services.audit import audit

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/stats", response_model=StatsOut)
def stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    today = datetime.combine(date.today(), datetime.min.time())
    tokens_today = db.scalar(
        select(func.coalesce(func.sum(Message.tokens), 0)).where(Message.created_at >= today)
    ) or 0
    questions_today = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.role == "user", Message.created_at >= today)
    ) or 0
    avg_latency = db.scalar(
        select(func.coalesce(func.avg(Message.latency_ms), 0)).where(Message.role == "assistant")
    ) or 0
    return StatsOut(
        users=db.scalar(select(func.count()).select_from(User)) or 0,
        kbs=db.scalar(select(func.count()).select_from(KnowledgeBase)) or 0,
        documents=db.scalar(select(func.count()).select_from(Document)) or 0,
        chunks=db.scalar(select(func.count()).select_from(Chunk)) or 0,
        conversations=db.scalar(select(func.count()).select_from(Conversation)) or 0,
        messages=db.scalar(select(func.count()).select_from(Message)) or 0,
        tokens_today=int(tokens_today),
        questions_today=int(questions_today),
        avg_latency_ms=int(avg_latency),
    )


@router.get("/users", response_model=list[UserOut])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [UserOut.model_validate(u) for u in db.scalars(select(User).order_by(User.id)).all()]


@router.post("/users", response_model=UserOut)
def create_user(
    body: UserCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status_code=400, detail="用户名已存在")
    if body.role not in {"admin", "user"}:
        raise HTTPException(status_code=400, detail="角色只能是 admin/user")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.username,
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, admin.id, "user_create", body.username, f"role={body.role}", client_ip(request))
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    is_active: bool | None = None,
    role: str | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id and is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    if is_active is not None:
        user.is_active = is_active
    if role is not None:
        if role not in {"admin", "user"}:
            raise HTTPException(status_code=400, detail="角色只能是 admin/user")
        user.role = role
    db.commit()
    return {"ok": True}


@router.get("/logs", response_model=list[AuditOut])
def logs(
    limit: int = 100,
    action: str | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return [AuditOut.model_validate(a) for a in db.scalars(stmt).all()]


@router.get("/system")
def system(admin: User = Depends(require_admin)):
    from ..config import settings

    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "llm": llm.health(),
        "embedding_model": settings.ollama_embed_model
        if settings.llm_provider == "ollama"
        else settings.openai_embed_model,
        "chunk_size": settings.chunk_size,
        "top_k": settings.top_k,
        "hybrid": settings.enable_hybrid,
    }
