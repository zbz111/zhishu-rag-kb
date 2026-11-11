"""切分：按段落合并 → 超长按句子滑窗。保证每块语义相对完整，并带 overlap。"""
from __future__ import annotations

import re

_SENT = re.compile(r"(?<=[。！？；!?;])")


def split_text(text: str, size: int = 600, overlap: int = 100) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    size = max(50, size)
    overlap = max(0, min(overlap, size // 2))

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    merged: list[str] = []
    buf = ""
    for para in paras:
        if len(buf) + len(para) + 1 <= size:
            buf = f"{buf}\n{para}" if buf else para
        else:
            if buf:
                merged.append(buf)
            buf = para
    if buf:
        merged.append(buf)

    chunks: list[str] = []
    for block in merged:
        if len(block) <= size:
            chunks.append(block)
            continue
        sentences: list[str] = []
        for para in block.split("\n"):
            sentences.extend([s for s in _SENT.split(para) if s])
        cur = ""
        for sent in sentences:
            if len(cur) + len(sent) <= size:
                cur += sent
            else:
                if cur:
                    chunks.append(cur)
                # 带 overlap：尾部保留一段，接到下一块开头
                tail = cur[-overlap:] if overlap and len(cur) > overlap else ""
                cur = tail + sent
                while len(cur) > size:
                    chunks.append(cur[:size])
                    cur = cur[size - overlap:]
        if cur.strip():
            chunks.append(cur)

    return [c.strip() for c in chunks if c.strip()]


def count_tokens_rough(text: str) -> int:
    """粗略 token 估算：中文按 1.5 字/token，英文按 4 字符/token。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = len(text) - cjk
    return int(cjk / 1.5 + other / 4) + 1
