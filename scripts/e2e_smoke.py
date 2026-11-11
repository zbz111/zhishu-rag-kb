"""端到端冒烟测试：登录 → 建库 → 上传 → 等待索引 → 问答 → 流式问答。

用法：.venv\\Scripts\\python.exe scripts\\e2e_smoke.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
SAMPLES = [
    Path("data/samples/员工手册.md"),
    Path("data/samples/产品手册_X1.md"),
]


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=120) as c:
        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        r.raise_for_status()
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("[1] 登录成功")

        r = c.get("/api/v1/kbs", headers=headers)
        kb = next((k for k in r.json() if k["name"] == "星海科技知识库"), None)
        if kb is None:
            r = c.post("/api/v1/kbs", headers=headers, json={"name": "星海科技知识库", "description": "员工手册与产品手册"})
            r.raise_for_status()
            kb = r.json()
        kb_id = kb["id"]
        print(f"[2] 知识库 id={kb_id}，已有 {kb['doc_count']} 篇文档")

        existing = {d["filename"] for d in c.get(f"/api/v1/kbs/{kb_id}/documents", headers=headers).json()}
        for path in SAMPLES:
            if path.name in existing:
                print(f"    - 已存在，跳过：{path.name}")
                continue
            with path.open("rb") as fh:
                r = c.post(f"/api/v1/kbs/{kb_id}/documents", headers=headers, files={"file": (path.name, fh, "text/markdown")})
            print(f"    - 上传 {path.name}: {r.status_code} {r.text[:120] if r.status_code >= 400 else 'ok'}")
            r.raise_for_status()

        print("[3] 等待索引完成...")
        for _ in range(60):
            docs = c.get(f"/api/v1/kbs/{kb_id}/documents", headers=headers).json()
            if all(d["status"] in {"ready", "failed"} for d in docs) and docs:
                break
            time.sleep(2)
        for d in docs:
            print(f"    {d['filename']}: {d['status']} chunks={d['chunk_count']} {d['error'][:80]}")

        print("[4] 普通问答")
        r = c.post("/api/v1/chat", headers=headers, json={"kb_id": kb_id, "question": "年假有几天？"})
        r.raise_for_status()
        data = r.json()
        print("    回答:", data["answer"].replace("\n", " ")[:200])
        print("    引用:", [(s["filename"], s["page"], s["score"]) for s in data["sources"]])
        print(f"    延迟 {data['latency_ms']}ms")

        print("[5] 流式问答")
        with c.stream(
            "POST",
            "/api/v1/chat/stream",
            headers=headers,
            json={"kb_id": kb_id, "question": "X1 标准版多少钱？保修多久？"},
        ) as resp:
            resp.raise_for_status()
            first = []
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if "t" in obj:
                        first.append(obj["t"])
                    if len("".join(first)) > 120:
                        break
        print("    流式前 120 字:", "".join(first)[:120].replace("\n", " "))

        print("[6] 无答案问题（测幻觉）")
        r = c.post("/api/v1/chat", headers=headers, json={"kb_id": kb_id, "question": "公司有没有海外仓？"})
        print("    回答:", r.json()["answer"][:120])

        print("[7] 统计")
        r = c.get("/api/v1/admin/stats", headers=headers)
        print("   ", r.json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
