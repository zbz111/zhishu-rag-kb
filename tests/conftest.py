"""pytest 公共配置：独立测试库 + 离线 hash embedding，不依赖模型服务。

注意：不使用 tempfile.mkdtemp（在部分沙箱环境下其目录不可写），改用项目内固定目录。
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = ROOT / ".testtmp"
if TMP.exists():
    shutil.rmtree(TMP, ignore_errors=True)
TMP.mkdir(parents=True, exist_ok=True)
(TMP / "uploads").mkdir(parents=True, exist_ok=True)

os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{(TMP / 'test.db').as_posix()}",
        "DATA_DIR": str(TMP),
        "UPLOAD_DIR": str(TMP / "uploads"),
        "LLM_PROVIDER": "hash",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "admin123",
        "SECRET_KEY": "test-secret-key-for-pytest-only",
        "ENABLE_HYBRID": "true",
        "CHUNK_SIZE": "300",
        "CHUNK_OVERLAP": "50",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}
