"""端到端评测：上传测试文档 → 建索引 → 跑测试问题集 → 出准确率报告。

用法：
    .venv\\Scripts\\python.exe scripts\\run_eval.py
    .venv\\Scripts\\python.exe scripts\\run_eval.py --kb 测试文档库 --reuse
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
DOC_DIR = Path("data/test_docs")
QA_FILE = DOC_DIR / "测试问题集.json"


def login(c: httpx.Client) -> dict:
    r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def ensure_kb(c: httpx.Client, h: dict, name: str) -> int:
    kbs = c.get("/api/v1/kbs", headers=h).json()
    for kb in kbs:
        if kb["name"] == name:
            return kb["id"]
    r = c.post("/api/v1/kbs", headers=h, json={"name": name, "description": "批量测试用"})
    r.raise_for_status()
    return r.json()["id"]


def upload_all(c: httpx.Client, h: dict, kb_id: int) -> None:
    existing = {d["filename"] for d in c.get(f"/api/v1/kbs/{kb_id}/documents", headers=h).json()}
    for f in sorted(DOC_DIR.iterdir()):
        if f.suffix.lower() not in {".pdf", ".docx", ".md", ".txt"}:
            continue
        if f.name in existing:
            print(f"  跳过（已存在）：{f.name}")
            continue
        with f.open("rb") as fh:
            r = c.post(f"/api/v1/kbs/{kb_id}/documents", headers=h, files={"file": (f.name, fh)})
        print(f"  上传 {f.name}: {r.status_code}")
        if r.status_code >= 400:
            print("    ->", r.text[:150])
        time.sleep(0.3)


def wait_ready(c: httpx.Client, h: dict, kb_id: int, timeout: int = 600) -> list[dict]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        docs = c.get(f"/api/v1/kbs/{kb_id}/documents", headers=h).json()
        busy = [d for d in docs if d["status"] in {"pending", "parsing", "indexing"}]
        if docs and not busy:
            return docs
        time.sleep(3)
    return c.get(f"/api/v1/kbs/{kb_id}/documents", headers=h).json()


def normalize(text: str) -> str:
    """归一化：去空白标点、统一同义符号，便于模糊比对。"""
    t = text
    for a, b in [("+", "加"), ("–", "-"), ("—", "-"), ("－", "-"), ("至", "-"), ("到", "-"), ("：", ":")]:
        t = t.replace(a, b)
    return re.sub(r"[\s,，。、（）()\[\]%％\"'·]", "", t)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def judge(answer: str, expected: str) -> tuple[bool, str]:
    """判定：
    - 无答案题：必须明确拒答；
    - 有答案题：先看精确命中，再看数字是否全部出现，最后做相似度比对。
    """
    if not expected:
        ok = "没有相关" in answer or "资料中" in answer
        return ok, "应拒答" if ok else "编造了答案"

    a_norm = normalize(answer)
    e_norm = normalize(expected)

    if e_norm and e_norm in a_norm:
        return True, "精确命中"

    exp_nums = _numbers(expected)
    got_nums = _numbers(answer)
    if exp_nums and exp_nums <= got_nums:
        return True, f"关键数字全中 {sorted(exp_nums)}"

    ratio = difflib.SequenceMatcher(None, e_norm, a_norm).ratio()
    if ratio >= 0.55:
        return True, f"相似度 {ratio:.2f}"

    parts = [p for p in re.split(r"[、，,/（）()]", expected) if normalize(p)]
    hit = sum(1 for p in parts if normalize(p) and normalize(p) in a_norm)
    if parts and hit / len(parts) >= 0.6:
        return True, f"关键词命中 {hit}/{len(parts)}"

    return False, f"未命中（期望「{expected}」，相似度 {ratio:.2f}）"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", default="测试文档库")
    ap.add_argument("--reuse", action="store_true", help="复用已建好的库，不重新上传")
    args = ap.parse_args()

    qa = json.loads(QA_FILE.read_text(encoding="utf-8"))

    with httpx.Client(base_url=BASE, timeout=180) as c:
        h = login(c)
        kb_id = ensure_kb(c, h, args.kb)
        print(f"知识库 id={kb_id}")

        if not args.reuse:
            upload_all(c, h, kb_id)

        print("等待索引完成 ...")
        docs = wait_ready(c, h, kb_id)
        ready = [d for d in docs if d["status"] == "ready"]
        failed = [d for d in docs if d["status"] == "failed"]
        print(f"  就绪 {len(ready)} 篇，失败 {len(failed)} 篇，共 {sum(d['chunk_count'] for d in docs)} 个分块")
        for d in failed:
            print(f"  失败：{d['filename']} -> {d['error'][:80]}")

        print(f"\n开始评测 {len(qa)} 条问题 ...\n")
        rows = []
        ok_count = 0
        latencies = []
        for i, item in enumerate(qa, 1):
            t0 = time.time()
            r = c.post("/api/v1/chat", headers=h, json={"kb_id": kb_id, "question": item["question"]})
            cost = time.time() - t0
            latencies.append(cost)
            if r.status_code != 200:
                rows.append({**item, "got": f"HTTP {r.status_code}", "ok": False, "why": "接口报错", "sec": round(cost, 2)})
                print(f"{i:2d}. [HTTP {r.status_code}] {item['question']}")
                continue
            data = r.json()
            ok, why = judge(data["answer"], item["answer"])
            ok_count += ok
            top = data["sources"][0]["filename"] if data["sources"] else "-"
            rows.append({**item, "got": data["answer"], "ok": ok, "why": why, "top": top, "sec": round(cost, 2)})
            flag = "✅" if ok else "❌"
            print(f"{i:2d}. {flag} {item['question']}")
            print(f"     答：{data['answer'][:80]}")
            if not ok:
                print(f"     ({why})")

        total = len(qa)
        answerable = [r for r in rows if r["answer"]]
        noanswer = [r for r in rows if not r["answer"]]
        acc = ok_count / total

        print("\n" + "=" * 60)
        print(f"总准确率      : {ok_count}/{total} = {acc:.1%}")
        if answerable:
            a_ok = sum(1 for r in answerable if r["ok"])
            print(f"有答案题      : {a_ok}/{len(answerable)} = {a_ok/len(answerable):.1%}")
        if noanswer:
            n_ok = sum(1 for r in noanswer if r["ok"])
            print(f"无答案题(拒答): {n_ok}/{len(noanswer)} = {n_ok/len(noanswer):.1%}")
        print(f"平均延迟      : {sum(latencies)/len(latencies):.2f}s")
        print(f"P95 延迟      : {sorted(latencies)[int(len(latencies)*0.95)]:.2f}s")

        out = Path("data/eval_report.json")
        out.write_text(
            json.dumps(
                {"kb": args.kb, "total": total, "accuracy": round(acc, 4), "rows": rows},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n明细已写入 {out}")


if __name__ == "__main__":
    main()