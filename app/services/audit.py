"""审计日志写入。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog


def audit(db: Session, user_id: int | None, action: str, target: str = "", detail: str = "", ip: str = "") -> None:
    db.add(AuditLog(user_id=user_id, action=action, target=target, detail=detail[:2000], ip=ip))
    db.commit()
