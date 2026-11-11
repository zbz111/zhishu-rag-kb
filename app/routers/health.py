"""健康检查：存活、就绪、模型状态。"""
from __future__ import annotations

from fastapi import APIRouter

from ..config import settings
from ..services import llm
from ..services.embeddings import probe_dim

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok", "version": settings.app_version}


@router.get("/readyz")
def readyz():
    info = llm.health()
    dim = probe_dim()
    ready = bool(info.get("ok")) and dim > 0
    return {
        "ready": ready,
        "llm": info,
        "embedding_dim": dim,
        "provider": settings.llm_provider,
    }
