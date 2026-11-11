<p align="center">
  <img src="docs/logo.svg" width="72" height="72" alt="知源" />
</p>

<h1 align="center">知源 · 企业知识库问答系统</h1>

<p align="center">
  私有化部署 · 答案可溯源 · 支持本地大模型 · 开箱即用
</p>

<p align="center">
  <img alt="python" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" />
  <img alt="fastapi" src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" />
  <img alt="vue" src="https://img.shields.io/badge/Vue-3.5-42B883?logo=vue.js&logoColor=white" />
  <img alt="license" src="https://img.shields.io/badge/License-MIT-blue" />
</p>

---

## 这是什么

**知源**是一个可以部署在公司内网的企业文档问答系统：管理员建知识库、上传 PDF/Word/Markdown，员工用自然语言提问，系统检索相关段落、让大模型基于资料回答，并标注答案来自哪份文件的第几页。

它不是一个 demo，而是一个可用的小型产品：有登录、有多用户与知识库授权、有审计日志与用量统计、有后台管理、有部署脚本与 Docker 镜像。

## 功能

**知识管理**
- 支持 PDF / DOCX / **XLSX（Excel，多工作表自动拆分）** / Markdown / TXT，单文件 30MB，同一内容自动去重（SHA-256）
- 上传后自动排队：解析 → 切分（段落合并 + 句子滑窗，可配 chunk/overlap）→ 向量化 → 入库
- 解析状态可见（排队/解析/建索引/就绪/失败+原因），支持一键重建、删除、下载

**检索与问答**
- 向量检索 + BM25 关键词检索，RRF 倒数排名融合（可关闭）
- 引用溯源：每个回答标注 `[1][2]`，前端可展开看原文片段与相似度
- 允许"无答案"：资料中确实没有时明确回答，不编造
- 多轮对话：自动带最近 3 轮上下文
- 流式输出（SSE），前端逐字渲染

**多用户与安全**
- JWT 登录、bcrypt 密码哈希、角色（admin/user）
- 知识库级授权：owner / editor / viewer 三种角色
- 全链路审计日志：登录、上传、删除、问答，记录 IP 与时间
- 密钥只放 `.env`，`.gitignore` 已排除

**运维与可观测**
- `/healthz` 存活、`/readyz` 就绪（含模型连通性探测）
- 结构化请求日志 + `x-request-id`
- 后台统计：今日提问数、Token、平均延迟、文档/分块/用户数
- SQLite 零依赖启动，可切 PostgreSQL；向量存储可替换为 Milvus/pgvector

## 架构

```text
┌──────────────┐   SSE 流式    ┌─────────────────────────────────────────┐
│  Vue3 + EP   │ ────────────▶ │              FastAPI                    │
│  (Vite 构建)  │ ◀──────────── │  auth · kbs · documents · chat · admin  │
└──────────────┘               └───────┬──────────────┬──────────────────┘
                                       │              │
                              ┌────────▼──────┐  ┌────▼─────────────┐
                              │  检索服务      │  │  模型服务         │
                              │ 向量 + BM25    │  │ Ollama / OpenAI  │
                              │ RRF 融合       │  │ 兼容接口          │
                              └────────┬──────┘  └──────────────────┘
                                       │
                    ┌──────────────────▼───────────────────┐
                    │  SQLite：用户/知识库/文档/分块/会话/审计 │
                    │  分块向量以 float32 BLOB 存储          │
                    └──────────────────────────────────────┘
```

**为什么向量不放 Chroma？** 单机万级分块下，SQLite + numpy 余弦检索（一次约几十毫秒）足够快，且零额外进程、零版本冲突；检索封装在 `services/vector_store.py`，换成 Milvus/pgvector 只需要替换 `search()`。

## 快速开始

### 方式一：本机运行（推荐给开发/演示）

```bash
# 1. 依赖
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate      # macOS / Linux
pip install -r requirements.txt

# 2. 配置
copy .env.example .env           # Windows
# cp .env.example .env           # macOS / Linux
# 编辑 .env：至少确认 LLM_PROVIDER 与模型名

# 3. 启动
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 ，用 `admin / admin123` 登录（**首次登录后请立即改密码**）。
API 文档：http://127.0.0.1:8000/api/docs

### 方式二：Docker

```bash
docker compose up -d --build
```

> **国内网络提示**：`registry-1.docker.io` 常被墙，拉基础镜像会超时。两种解法：
>
> 1）Docker Desktop → Settings → Docker Engine 的 JSON 里加镜像源（改完 Apply & restart）：
>
> ```json
> {
>   "registry-mirrors": ["https://docker.m.daocloud.io", "https://docker.1ms.run"]
> }
> ```
>
> 2）或者逐个拉取再重命名：
>
> ```bash
> docker pull docker.m.daocloud.io/library/python:3.12-slim
> docker tag  docker.m.daocloud.io/library/python:3.12-slim python:3.12-slim
> ```
>
> 第三方镜像源能看到你拉取的镜像，**只建议用于公开基础镜像**，公司私有镜像请走自己的 registry。

### 模型准备

默认走本地 **Ollama**（免费、断网可用、数据不出内网）：

```bash
ollama pull qwen2.5:7b        # 对话模型
ollama pull bge-m3            # 向量模型（中文效果好）
ollama serve
```

想用 DeepSeek / 通义等云端模型，改 `.env`：

```bash
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=sk-xxxx
OPENAI_CHAT_MODEL=deepseek-chat
```

> 注意：切换向量模型后维度可能变化，需要在「文档管理」里对已有文档逐个「重建索引」。

## 配置项

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` / `openai` |
| `OLLAMA_CHAT_MODEL` | `qwen2.5:7b` | 对话模型 |
| `OLLAMA_EMBED_MODEL` | `bge-m3` | 向量模型 |
| `CHUNK_SIZE` | `600` | 分块字符数 |
| `CHUNK_OVERLAP` | `100` | 分块重叠 |
| `TOP_K` | `6` | 最终返回给模型的片段数 |
| `CANDIDATE_K` | `20` | 每路召回候选数 |
| `ENABLE_HYBRID` | `true` | 是否开启 BM25 混合检索 |
| `HISTORY_TURNS` | `3` | 多轮上下文轮数 |
| `MAX_UPLOAD_MB` | `30` | 上传大小上限 |
| `SECRET_KEY` | - | **生产环境必须替换** |

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/login` | 登录获取 JWT |
| GET | `/api/v1/auth/me` | 当前用户 |
| GET/POST | `/api/v1/kbs` | 知识库列表 / 创建 |
| PATCH/DELETE | `/api/v1/kbs/{id}` | 修改 / 删除 |
| GET | `/api/v1/kbs/{id}/members` | 成员列表 |
| POST | `/api/v1/kbs/{id}/documents` | 上传文档 |
| GET | `/api/v1/kbs/{id}/documents` | 文档列表与状态 |
| POST | `/api/v1/documents/{id}/reindex` | 重建索引 |
| POST | `/api/v1/chat` | 问答（非流式） |
| POST | `/api/v1/chat/stream` | 问答（SSE 流式） |
| POST | `/api/v1/chat/feedback` | 点赞/点踩 |
| GET | `/api/v1/admin/stats` | 用量统计 |
| GET | `/api/v1/admin/logs` | 审计日志 |

## 测试与评测

```bash
pytest                         # 7 个接口测试：认证、权限、上传入库、问答引用
python scripts/e2e_smoke.py    # 端到端冒烟（需服务已启动）
python scripts/make_test_docs.py  # 生成 8 篇测试文档（PDF/DOCX/MD/TXT）
python scripts/run_eval.py     # 28 题评测，自动出准确率
```

### 评测结果（28 题，含 3 条无答案题）

| 指标 | 结果 |
|---|---|
| 总准确率 | **28/28 = 100%** |
| 有答案题 | 25/25 |
| 无答案题（应拒答） | 3/3（0 编造） |
| 平均延迟 | 1.48 s |
| P95 延迟 | 2.39 s |

> 样本量偏小（28 条）且题目与语料同源，属"自建自测"；正式业务应扩到 200 条以上并人工复核。

## 目录

```text
rag_kb/
  app/
    main.py            # 应用入口、静态前端、启动自检
    config.py          # 全部配置（pydantic-settings）
    models.py          # 用户/知识库/文档/分块/会话/消息/审计
    routers/           # auth / kbs / documents / chat / admin / health
    services/
      parser.py        # PDF / DOCX / MD 解析
      splitter.py      # 段落合并 + 句滑窗切分
      embeddings.py    # Ollama / OpenAI / hash 三种 embedding
      vector_store.py  # SQLite + numpy 余弦检索
      retrieval.py     # 向量 + BM25 + RRF
      ingest.py        # 后台索引流水线
      rag.py           # Prompt 编排、引用、流式
      llm.py           # 对话模型适配
    static/            # 预构建前端（无需 node 即可运行）
  frontend/            # Vue3 + Element Plus 源码
  tests/
  scripts/
  data/samples/        # 示例文档
```

## 已知边界

- 单机单租户，未做多租户隔离与 SSO
- 扫描版 PDF（图片）不支持，需 OCR，属 Roadmap
- 向量检索为暴力计算，十万级以上分块建议换 Milvus/pgvector
- 前端为预构建产物，二次开发需 `cd frontend && npm install && npm run build`

## Roadmap

- [ ] OCR / 表格结构化解析
- [ ] 查询改写（多轮指代消解）
- [ ] rerank（bge-reranker）
- [ ] 评测面板（导入 QA 集，跑分对比）
- [ ] 企业微信 / 钉钉机器人
- [ ] PostgreSQL + pgvector 后端

## License

MIT

