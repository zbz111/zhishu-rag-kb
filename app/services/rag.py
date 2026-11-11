"""RAG 编排：检索 → 组装 Prompt → 调用模型 → 输出答案与引用。"""
from __future__ import annotations

import re
import time
from collections.abc import Iterator

from sqlalchemy.orm import Session

from ..config import settings
from . import llm, retrieval

NO_ANSWER = "资料中没有相关信息"

SYSTEM_PROMPT = f"""你是企业知识库助手，只能依据给定的【资料】回答。

规则：
1. 只使用【资料】中的信息，禁止使用你自己的知识补充。
2. 资料中没有答案时，只回复这一句：{NO_ANSWER}
3. 引用资料时在句末标注编号，格式固定为 [1]、[2]，一个方括号里只能有一个数字。
   禁止写成 [1.2]、[1-2]、[1][2]、[3.1] 这类形式。
4. 编号必须与【资料】中每个片段开头的编号一一对应，不能超出范围。
5. 问题包含多个要点（出现"和""分别""各""以及"等连接、或连续问了两件事）时，
   必须逐条回答，每个要点单独给出，不能只答其中一个。
6. 回答控制在 6 句以内，先给结论，再给依据。
7. 资料中若有标注【表格】的内容，按行列关系理解数据后再作答。
8. 如果资料互相矛盾，指出矛盾并分别标注来源。
"""


def build_context(hits: list[dict], max_chars: int = 6000) -> str:
    parts: list[str] = []
    used = 0
    for i, h in enumerate(hits, start=1):
        block = f"[{i}] 来源：{h['filename']} 第{h['page']}页\n{h['text']}"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def build_messages(question: str, hits: list[dict], history: list[dict] | None = None) -> list[dict]:
    context = build_context(hits)
    allowed = "、".join(f"[{i}]" for i in range(1, len(hits) + 1))
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-settings.history_turns * 2 :]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append(
        {
            "role": "user",
            "content": (
                f"【资料】\n{context}\n\n【问题】\n{question}\n\n"
                f"可用的引用编号只有：{allowed}。请依据资料回答，并只用这些编号标注引用。"
            ),
        }
    )
    return messages


_CITE = re.compile(r"\[\s*(\d+)(?:\s*[.\-–]\s*\d+)*\s*\]")


def normalize_citations(text: str, n_sources: int) -> str:
    """把 [3.1] / [1-2] 之类非法引用规范为 [3]，并删除超出范围的编号。"""

    def _fix(m: re.Match[str]) -> str:
        first = int(m.group(1))
        return f"[{first}]" if 1 <= first <= n_sources else ""

    fixed = _CITE.sub(_fix, text)
    fixed = re.sub(r"[ \t]+（\s*）", "", fixed)
    fixed = re.sub(r"[ \t]{2,}", " ", fixed)
    return fixed.strip()


_SHEET = re.compile(r"工作表：([^（(\n]+)")


def _sheet_of(text: str) -> str:
    """Excel 分块开头带有「工作表：xxx」，抽出来当位置标签，比空泛的"第 1 页"有用。"""
    m = _SHEET.search(text[:120])
    return m.group(1).strip() if m else ""


def to_sources(hits: list[dict]) -> list[dict]:
    out = []
    for i, h in enumerate(hits, start=1):
        sheet = _sheet_of(h["text"])
        if not sheet and h["filename"].lower().endswith((".xlsx", ".xlsm")):
            # 只有该工作表的第一个分块带表头，其余用序号兜底
            sheet = str(h["page"])
        out.append(
            {
                "index": i,
                "document_id": h["document_id"],
                "filename": h["filename"],
                "page": h["page"],
                "sheet": sheet,
                "chunk_id": h["chunk_id"],
                "score": round(float(h["score"]), 4),
                "snippet": h["text"][:300],
            }
        )
    return out


def postprocess(text: str, n_sources: int = 0) -> str:
    """清洗模型输出：
    1) "无答案"话术统一成固定回复（去掉模型顺手加的引用）；
    2) 非法引用（[3.1] / [1-2] / 超范围编号）规范化或删除。
    """
    t = text.strip()
    if NO_ANSWER in t[:40]:
        return NO_ANSWER
    if n_sources:
        t = normalize_citations(t, n_sources)
    return t


def answer(db: Session, kb_id: int, question: str, history: list[dict] | None = None) -> dict:
    t0 = time.time()
    hits = retrieval.hydrate(db, retrieval.retrieve(db, kb_id, question))
    sources = to_sources(hits)
    if not hits:
        return {
            "answer": NO_ANSWER,
            "sources": [],
            "tokens": 0,
            "latency_ms": int((time.time() - t0) * 1000),
        }
    text, tokens = llm.chat(build_messages(question, hits, history))
    return {
        "answer": postprocess(text, len(sources)),
        "sources": sources,
        "tokens": tokens,
        "latency_ms": int((time.time() - t0) * 1000),
    }


def answer_stream(
    db: Session, kb_id: int, question: str, history: list[dict] | None = None
) -> Iterator[tuple[str, object]]:
    """产出 (event, payload)：sources → token* → done。"""
    t0 = time.time()
    hits = retrieval.hydrate(db, retrieval.retrieve(db, kb_id, question))
    sources = to_sources(hits)
    if not hits:
        yield "sources", []
        yield "token", NO_ANSWER
        yield "done", {"tokens": 0, "latency_ms": int((time.time() - t0) * 1000)}
        return

    yield "sources", sources
    n_sources = len(sources)
    collected: list[str] = []
    head = ""
    flushed = False
    for piece in llm.stream_chat(build_messages(question, hits, history)):
        collected.append(piece)
        if not flushed:
            head += piece
            if len(head) >= 40:
                if NO_ANSWER in head[:40]:
                    yield "token", NO_ANSWER
                    flushed = True
                    head = ""
                else:
                    yield "token", head
                    flushed = True
            continue
        yield "token", piece
    if not flushed and head:
        yield "token", postprocess(head, n_sources)
    yield "done", {
        "tokens": 0,
        "latency_ms": int((time.time() - t0) * 1000),
        "content": postprocess("".join(collected), n_sources),
    }
