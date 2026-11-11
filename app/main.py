"""FastAPI 入口：路由注册、请求日志、静态前端、启动自检。"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select

from .config import settings
from .db import SessionLocal, init_db
from .models import User
from .routers import admin, auth, chat, documents, health, kbs
from .security import hash_password
from .services.embeddings import probe_dim
from .services.llm import health as llm_health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("app")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="企业知识库问答系统：文档解析、混合检索、引用溯源、多用户权限。",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.time()
    response = await call_next(request)
    cost = int((time.time() - started) * 1000)
    response.headers["x-request-id"] = request_id
    if not request.url.path.startswith(("/static", "/assets")):
        logger.info("%s %s %s %sms id=%s", request.method, request.url.path, response.status_code, cost, request_id)
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(kbs.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(admin.router)

STATIC_DIR = Path(__file__).parent / "static"
ASSETS_DIR = STATIC_DIR / "assets"

if ASSETS_DIR.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        {
            "message": "前端尚未构建。开发模式请运行 frontend 的 npm run dev；生产模式请先 npm run build。",
            "api_docs": "/api/docs",
        }
    )


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith(("api/", "assets/", "healthz", "readyz")):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    candidate = STATIC_DIR / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"detail": "Not Found"}, status_code=404)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    with SessionLocal() as db:
        admin_user = db.scalar(select(User).where(User.username == settings.admin_username))
        if admin_user is None:
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    display_name="管理员",
                    role="admin",
                )
            )
            db.commit()
            logger.warning(
                "已创建默认管理员 %s / %s —— 请立即登录后修改密码",
                settings.admin_username,
                settings.admin_password,
            )
    info = llm_health()
    dim = probe_dim()
    logger.info("模型服务 %s | chat=%s | embed=%s | dim=%s", info.get("ok"), info.get("chat_model"), info.get("embed_model"), dim)
    if not info.get("ok"):
        logger.warning("模型服务不可达，请检查 Ollama 是否启动（ollama serve）")
