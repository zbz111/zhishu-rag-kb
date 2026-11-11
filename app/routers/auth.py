"""认证：登录、当前用户、改密、注册（可选）。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import client_ip, get_current_user
from ..models import User
from ..schemas import LoginRequest, PasswordChange, TokenResponse, UserCreate, UserOut
from ..security import create_access_token, hash_password, verify_password
from ..services.audit import audit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        audit(db, None, "login_failed", body.username, ip=client_ip(request))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已禁用")

    user.last_login_at = datetime.now()
    db.commit()
    audit(db, user.id, "login", user.username, ip=client_ip(request))

    token = create_access_token(user.id, user.username, user.role)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.post("/change-password")
def change_password(
    body: PasswordChange,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不正确")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    audit(db, user.id, "change_password", user.username, ip=client_ip(request))
    return {"ok": True}


@router.post("/register", response_model=UserOut)
def register(body: UserCreate, request: Request, db: Session = Depends(get_db)):
    if not settings.allow_register:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="未开放注册，请联系管理员开通账号")
    exists = db.scalar(select(func.count()).select_from(User).where(User.username == body.username))
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.username,
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, user.id, "register", user.username, ip=client_ip(request))
    return UserOut.model_validate(user)
