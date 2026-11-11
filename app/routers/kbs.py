"""知识库：增删改查 + 成员授权。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import client_ip, get_current_user, kb_role, require_kb_access
from ..models import Document, KBMember, KnowledgeBase, User
from ..schemas import KBCreate, KBOut, KBUpdate, MemberIn, UserOut
from ..services.audit import audit

router = APIRouter(prefix="/api/v1/kbs", tags=["knowledge-bases"])


def _to_out(db: Session, kb: KnowledgeBase, role: str) -> KBOut:
    doc_count = db.scalar(select(func.count()).select_from(Document).where(Document.kb_id == kb.id)) or 0
    return KBOut(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        owner_id=kb.owner_id,
        doc_count=doc_count,
        my_role=role,
        created_at=kb.created_at,
    )


@router.get("", response_model=list[KBOut])
def list_kbs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kbs = db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.id.desc())).all()
    out: list[KBOut] = []
    for kb in kbs:
        role = kb_role(db, kb, user)
        if role:
            out.append(_to_out(db, kb, role))
    return out


@router.post("", response_model=KBOut, status_code=status.HTTP_201_CREATED)
def create_kb(
    body: KBCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = KnowledgeBase(name=body.name.strip(), description=body.description.strip(), owner_id=user.id)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    db.add(KBMember(kb_id=kb.id, user_id=user.id, role="owner"))
    db.commit()
    audit(db, user.id, "kb_create", kb.name, ip=client_ip(request))
    return _to_out(db, kb, "owner")


@router.patch("/{kb_id}", response_model=KBOut)
def update_kb(
    kb_id: int,
    body: KBUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb, role = require_kb_access(kb_id, user, db, need="owner")
    if body.name is not None:
        kb.name = body.name.strip() or kb.name
    if body.description is not None:
        kb.description = body.description.strip()
    db.commit()
    return _to_out(db, kb, role)


@router.delete("/{kb_id}")
def delete_kb(
    kb_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb, _ = require_kb_access(kb_id, user, db, need="owner")
    db.delete(kb)
    db.commit()
    audit(db, user.id, "kb_delete", kb.name, ip=client_ip(request))
    return {"ok": True}


@router.get("/{kb_id}/members", response_model=list[dict])
def list_members(
    kb_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_kb_access(kb_id, user, db, need="owner")
    rows = db.execute(
        select(KBMember, User).join(User, User.id == KBMember.user_id).where(KBMember.kb_id == kb_id)
    ).all()
    return [
        {"user_id": u.id, "username": u.username, "display_name": u.display_name, "role": m.role}
        for m, u in rows
    ]


@router.post("/{kb_id}/members")
def add_member(
    kb_id: int,
    body: MemberIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_kb_access(kb_id, user, db, need="owner")
    if body.role not in {"editor", "viewer", "owner"}:
        raise HTTPException(status_code=400, detail="角色只能是 owner/editor/viewer")
    target = db.get(User, body.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    member = db.scalar(select(KBMember).where(KBMember.kb_id == kb_id, KBMember.user_id == body.user_id))
    if member:
        member.role = body.role
    else:
        db.add(KBMember(kb_id=kb_id, user_id=body.user_id, role=body.role))
    db.commit()
    return {"ok": True}


@router.delete("/{kb_id}/members/{user_id}")
def remove_member(
    kb_id: int, user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    require_kb_access(kb_id, user, db, need="owner")
    member = db.scalar(select(KBMember).where(KBMember.kb_id == kb_id, KBMember.user_id == user_id))
    if member:
        db.delete(member)
        db.commit()
    return {"ok": True}


@router.get("/{kb_id}/candidates", response_model=list[UserOut])
def member_candidates(
    kb_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """可添加为成员的候选用户（仅管理员/库主）。"""
    require_kb_access(kb_id, user, db, need="owner")
    users = db.scalars(select(User).order_by(User.id)).all()
    return [UserOut.model_validate(u) for u in users]
