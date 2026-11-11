"""依赖注入：当前用户、管理员校验、知识库权限。"""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import KBMember, KnowledgeBase, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if cred is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        payload = decode_token(cred.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效凭证") from exc

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def get_kb_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    return kb


def kb_role(db: Session, kb: KnowledgeBase, user: User) -> str | None:
    """返回 owner / editor / viewer，无权限返回 None。"""
    if user.role == "admin" or kb.owner_id == user.id:
        return "owner"
    if kb.is_public:
        member = db.scalar(select(KBMember).where(KBMember.kb_id == kb.id, KBMember.user_id == user.id))
        return member.role if member else "viewer"
    member = db.scalar(select(KBMember).where(KBMember.kb_id == kb.id, KBMember.user_id == user.id))
    return member.role if member else None


def require_kb_access(
    kb_id: int, user: User, db: Session, need: str = "viewer"
) -> tuple[KnowledgeBase, str]:
    kb = get_kb_or_404(db, kb_id)
    role = kb_role(db, kb, user)
    if role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该知识库")
    order = {"viewer": 0, "editor": 1, "owner": 2}
    if order[role] < order[need]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return kb, role


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""
