"""请求 / 响应模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---------- 认证 ----------
class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool = True

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""
    role: str = "user"


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


# ---------- 知识库 ----------
class KBCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""


class KBUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class KBOut(BaseModel):
    id: int
    name: str
    description: str
    owner_id: int
    doc_count: int = 0
    my_role: str = "viewer"
    created_at: datetime | None = None


class MemberIn(BaseModel):
    user_id: int
    role: str = "viewer"


# ---------- 文档 ----------
class DocumentOut(BaseModel):
    id: int
    kb_id: int
    filename: str
    size: int
    status: str
    error: str = ""
    chunk_count: int = 0
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------- 对话 ----------
class ChatRequest(BaseModel):
    kb_id: int
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: int | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class SourceOut(BaseModel):
    index: int
    document_id: int
    filename: str
    page: int
    sheet: str = ""  # Excel 工作表名，有则优先展示
    chunk_id: int
    score: float
    snippet: str


class ChatResponse(BaseModel):
    conversation_id: int
    message_id: int
    answer: str
    sources: list[SourceOut]
    tokens: int
    latency_ms: int


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: list[SourceOut] = []
    tokens: int = 0
    latency_ms: int = 0
    created_at: datetime | None = None


class ConversationOut(BaseModel):
    id: int
    kb_id: int
    title: str
    updated_at: datetime | None = None


class FeedbackIn(BaseModel):
    message_id: int
    rating: int = Field(ge=-1, le=1)
    reason: str = ""


# ---------- 管理 ----------
class StatsOut(BaseModel):
    users: int
    kbs: int
    documents: int
    chunks: int
    conversations: int
    messages: int
    tokens_today: int
    questions_today: int
    avg_latency_ms: int


class AuditOut(BaseModel):
    id: int
    user_id: int | None
    action: str
    target: str
    detail: str
    ip: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


TokenResponse.model_rebuild()
