"""对话：会话管理、流式问答、反馈。"""
from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, get_db
from ..deps import client_ip, get_current_user, require_kb_access
from ..models import Conversation, Feedback, Message, User
from ..schemas import (
    ChatRequest,
    ChatResponse,
    ConversationOut,
    FeedbackIn,
    MessageOut,
    SourceOut,
)
from ..services import rag
from ..services.audit import audit

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _history(db: Session, conversation_id: int) -> list[dict]:
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(settings.history_turns * 2)
    ).all()
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def _ensure_conversation(db: Session, kb_id: int, user_id: int, conversation_id: int | None, question: str):
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv is None or conv.user_id != user_id or conv.kb_id != kb_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        return conv
    conv = Conversation(kb_id=kb_id, user_id=user_id, title=question[:30] or "新对话")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    kb_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if kb_id:
        stmt = stmt.where(Conversation.kb_id == kb_id)
    convs = db.scalars(stmt.order_by(Conversation.updated_at.desc()).limit(100)).all()
    return [
        ConversationOut(id=c.id, kb_id=c.kb_id, title=c.title, updated_at=c.updated_at) for c in convs
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def conversation_messages(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
    ).all()
    out = []
    for m in msgs:
        sources = json.loads(m.sources or "[]")
        out.append(
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=[SourceOut(**s) for s in sources],
                tokens=m.tokens,
                latency_ms=m.latency_ms,
                created_at=m.created_at,
            )
        )
    return out


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(conv)
    db.commit()
    return {"ok": True}


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_kb_access(body.kb_id, user, db, need="viewer")
    conv = _ensure_conversation(db, body.kb_id, user.id, body.conversation_id, body.question)
    history = _history(db, conv.id)

    try:
        result = rag.answer(db, body.kb_id, body.question, history)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    db.add(Message(conversation_id=conv.id, role="user", content=body.question))
    msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=result["answer"],
        sources=json.dumps(result["sources"], ensure_ascii=False),
        tokens=result["tokens"],
        latency_ms=result["latency_ms"],
    )
    db.add(msg)
    conv.updated_at = func.now()
    db.commit()
    db.refresh(msg)
    audit(db, user.id, "chat", f"kb={body.kb_id}", body.question[:200], client_ip(request))

    return ChatResponse(
        conversation_id=conv.id,
        message_id=msg.id,
        answer=result["answer"],
        sources=[SourceOut(**s) for s in result["sources"]],
        tokens=result["tokens"],
        latency_ms=result["latency_ms"],
    )


@router.post("/chat/stream")
def chat_stream(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_kb_access(body.kb_id, user, db, need="viewer")
    conv = _ensure_conversation(db, body.kb_id, user.id, body.conversation_id, body.question)
    history = _history(db, conv.id)
    conv_id = conv.id
    kb_id = body.kb_id
    question = body.question
    user_id = user.id

    db.add(Message(conversation_id=conv_id, role="user", content=question))
    db.commit()

    def event_stream() -> Iterator[str]:
        session = SessionLocal()
        collected: list[str] = []
        sources: list[dict] = []
        tokens = 0
        latency = 0
        final_text = ""
        try:
            for event, payload in rag.answer_stream(session, kb_id, question, history):
                if event == "sources":
                    sources = payload  # type: ignore[assignment]
                    yield f"event: sources\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif event == "token":
                    collected.append(str(payload))
                    yield f"event: token\ndata: {json.dumps({'t': payload}, ensure_ascii=False)}\n\n"
                elif event == "done":
                    tokens = int(payload.get("tokens", 0))  # type: ignore[union-attr]
                    latency = int(payload.get("latency_ms", 0))  # type: ignore[union-attr]
                    final_text = str(payload.get("content", ""))  # type: ignore[union-attr]

            # 入库用清洗后的文本（引用编号已规范化）
            answer_text = final_text or "".join(collected)
            msg = Message(
                conversation_id=conv_id,
                role="assistant",
                content=answer_text,
                sources=json.dumps(sources, ensure_ascii=False),
                tokens=tokens,
                latency_ms=latency,
            )
            session.add(msg)
            session.commit()
            session.refresh(msg)
            yield (
                "event: done\ndata: "
                + json.dumps(
                    {"message_id": msg.id, "conversation_id": conv_id, "tokens": tokens, "latency_ms": latency},
                    ensure_ascii=False,
                )
                + "\n\n"
            )
        except Exception as exc:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            session.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/feedback")
def feedback(
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    msg = db.get(Message, body.message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    db.add(Feedback(message_id=msg.id, user_id=user.id, rating=body.rating, reason=body.reason[:500]))
    db.commit()
    return {"ok": True}
