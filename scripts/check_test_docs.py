"""检查测试文档的解析与切分质量（不依赖服务，直接调库）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.parser import parse_file  # noqa: E402
from app.services.splitter import split_text  # noqa: E402

DOCS = sorted(Path("data/test_docs").glob("*"))
for f in DOCS:
    if f.suffix.lower() not in {".pdf", ".docx", ".md", ".txt"}:
        continue
    try:
        blocks = parse_file(str(f))
    except Exception as exc:  # noqa: BLE001
        print(f"--- {f.name} --- 解析失败: {exc}")
        continue
    total = sum(len(b["text"]) for b in blocks)
    chunks = sum(len(split_text(b["text"], 600, 100)) for b in blocks)
    print(f"--- {f.name} ---")
    print(f"    块(页)数: {len(blocks)}   总字符: {total}   切分后: {chunks}")
    print(f"    开头: {blocks[0]['text'][:60]!r}")
    if len(blocks) > 1:
        print(f"    第2块: {blocks[1]['text'][:60]!r}")