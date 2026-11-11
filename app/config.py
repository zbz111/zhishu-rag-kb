"""全局配置：全部从环境变量 / .env 读取，代码里不出现任何硬编码密钥。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 基础
    app_name: str = "企业知识库问答系统"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = 8000

    # 安全
    secret_key: str = "change-me-in-production-please-use-a-random-string"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 8 * 60
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # 数据库
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"
    data_dir: Path = BASE_DIR / "data"
    upload_dir: Path = BASE_DIR / "data" / "uploads"

    # 向量库（内置 SQLite + numpy 实现，零外部依赖；可替换为 Milvus/pgvector）
    vector_dim: int = 1024
    vector_store: str = "sqlite"  # sqlite | chroma

    # 模型服务
    llm_provider: str = "ollama"  # ollama | openai
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "bge-m3"

    openai_base_url: str = "https://api.deepseek.com"
    openai_api_key: str = ""
    openai_chat_model: str = "deepseek-chat"
    openai_embed_model: str = "bge-m3"
    openai_embed_base_url: str = "https://api.siliconflow.cn/v1"
    openai_embed_api_key: str = ""
    # 单次 embedding 请求的最大条数：阿里云 text-embedding-v3 上限 10
    embed_batch_size: int = 10

    # 检索
    chunk_size: int = 600
    chunk_overlap: int = 100
    top_k: int = 6
    candidate_k: int = 20
    enable_hybrid: bool = True
    enable_rerank: bool = False
    rerank_model: str = "BAAI/bge-reranker-base"
    # 检索结果过滤：低于绝对阈值、且明显低于最高分的结果直接丢弃
    min_similarity: float = 0.25
    similarity_ratio: float = 0.82

    # 生成
    temperature: float = 0.1
    max_tokens: int = 1200
    stream: bool = True
    history_turns: int = 3

    # 限额
    max_upload_mb: int = 30
    max_questions_per_day: int = 300
    rate_limit_per_minute: int = 20

    # 业务
    allow_register: bool = False

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()

