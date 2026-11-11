"""接口测试：认证、知识库、上传入库、问答检索、权限。"""
from __future__ import annotations

import io


def test_health(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_login_wrong_password(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "bad-password"})
    assert r.status_code == 401


def test_me(client, auth):
    r = client.get("/api/v1/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_kb_crud(client, auth):
    r = client.post("/api/v1/kbs", json={"name": "测试库", "description": "pytest"}, headers=auth)
    assert r.status_code == 201, r.text
    kb_id = r.json()["id"]

    r = client.get("/api/v1/kbs", headers=auth)
    assert any(k["id"] == kb_id for k in r.json())

    r = client.patch(f"/api/v1/kbs/{kb_id}", json={"name": "改名后的库"}, headers=auth)
    assert r.json()["name"] == "改名后的库"


def test_upload_ingest_and_chat(client, auth):
    kb_id = client.post("/api/v1/kbs", json={"name": "知识库A"}, headers=auth).json()["id"]

    content = (
        "员工手册\n\n"
        "第一条 年假：入职满一年享有 5 天带薪年假，满三年 10 天。\n\n"
        "第二条 报销：差旅费用需在回程后 15 天内提交，逾期不予报销。\n\n"
        "第三条 加班：工作日加班按 1.5 倍计算，周末按 2 倍计算。\n"
    ).encode("utf-8")

    r = client.post(
        f"/api/v1/kbs/{kb_id}/documents",
        files={"file": ("handbook.md", io.BytesIO(content), "text/markdown")},
        headers=auth,
    )
    assert r.status_code == 201, r.text
    doc = r.json()

    detail = client.get(f"/api/v1/kbs/{kb_id}/documents", headers=auth).json()[0]
    assert detail["status"] == "ready", detail
    assert detail["chunk_count"] >= 1

    r = client.post(
        "/api/v1/chat",
        json={"kb_id": kb_id, "question": "年假有几天？"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sources"], "应返回引用来源"
    assert body["sources"][0]["filename"] == "handbook.md"

    convs = client.get(f"/api/v1/conversations?kb_id={kb_id}", headers=auth).json()
    assert convs and convs[0]["id"] == body["conversation_id"]


def test_permission_isolation(client, auth):
    # 普通用户看不到未授权知识库
    r = client.post(
        "/api/v1/admin/users",
        json={"username": "user1", "password": "user123", "display_name": "普通用户"},
        headers=auth,
    )
    assert r.status_code == 200, r.text

    token = client.post("/api/v1/auth/login", json={"username": "user1", "password": "user123"}).json()[
        "access_token"
    ]
    user_auth = {"Authorization": f"Bearer {token}"}

    kb_id = client.post("/api/v1/kbs", json={"name": "管理员私有库"}, headers=auth).json()["id"]
    r = client.get(f"/api/v1/kbs/{kb_id}/documents", headers=user_auth)
    assert r.status_code == 403


def test_admin_stats(client, auth):
    r = client.get("/api/v1/admin/stats", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert data["users"] >= 2
    assert data["kbs"] >= 1
