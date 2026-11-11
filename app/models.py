"""数据模型：用户、知识库、成员、文档、会话、消息、反馈、审计。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)  # admin | user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class KBMember(Base):
    __tablename__ = "kb_members"
    __table_args__ = (UniqueConstraint("kb_id", "user_id", name="uq_kb_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="viewer", nullable=False)  # owner|editor|viewer
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending|parsing|indexing|ready|failed
    error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128), default="新对话", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Message(Base, TimestampMixin):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON
    tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    kb_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    page: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Feedback(Base, TimestampMixin):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 good, -1 bad
    reason: Mapped[str] = mapped_column(String(512), default="", nullable=False)


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ip: Mapped[str] = mapped_column(String(64), default="", nullable=False)
