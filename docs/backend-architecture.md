# Train Agent 后端架构设计文档

> 本文档面向 AI 及开发者，旨在帮助快速理解 Train Agent 后端的整体设计、模块职责与数据流转。

---

## 一、系统总览

Train Agent 后端由 **两个独立进程** 组成，共享同一份代码库：

| 进程 | 框架 | 端口 | 职责 |
|------|------|-----:|------|
| **FastAPI 服务** | FastAPI + Uvicorn | 8000 | REST API：工作区/文档/任务/消息 CRUD、文件上传与下载 |
| **LangGraph 服务** | LangGraph Server | 2024 | Agent 运行时：流式对话、工具调用、中断恢复 |

两个进程共享底层存储（SQLite + ChromaDB + 文件系统），但各自独立初始化依赖实例。

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Next.js :3000)                      │
│                                                                 │
│   REST API 调用 ──────────┐     LangGraph Stream ──────────┐    │
└───────────────────────────┼─────────────────────────────────┼────┘
                            ▼                                 ▼
                 ┌─────────────────┐              ┌──────────────────┐
                 │  FastAPI (:8000) │              │ LangGraph (:2024)│
                 │                 │              │                  │
                 │  routes.py      │              │  graph.py        │
                 │  deps.py        │              │  state.py        │
                 │  doc_service.py │              │  prompt_manager  │
                 └────────┬────────┘              │  skill_manager   │
                          │                       │  middlewares/*   │
                          │                       │  tools/*         │
                          │                       └────────┬─────────┘
                          │                                │
                          ▼                                ▼
                 ┌─────────────────────────────────────────────────┐
                 │              共享存储层                           │
                 │                                                 │
                 │  SQLite (database.py)   ← 元数据: workspace,    │
                 │                            document, task,      │
                 │                            message              │
                 │  ChromaDB (vector_store.py) ← 向量索引           │
                 │  FileStore (file_store.py)  ← 原始文件 + 产出    │
                 └─────────────────────────────────────────────────┘
```

---

## 二、技术栈

| 类别 | 技术 | 版本要求 | 说明 |
|------|------|---------|------|
| **语言** | Python | ≥ 3.12 | 使用 `match` 等新语法特性 |
| **Web 框架** | FastAPI | ≥ 0.115 | 异步 REST API |
| **Agent 框架** | LangChain + LangGraph | LangChain ≥ 1.2, LangGraph ≥ 1.1 | Agent 编排、中间件、工具注册 |
| **LLM 接入** | langchain-openai + DeepSeek | — | 通过 OpenAI 兼容接口调用 DeepSeek (deepseek-v4-flash) |
| **TTS** | Dashscope qwen3-tts-flash | — | 口播稿音频合成，非流式调用 |
| **向量数据库** | ChromaDB | ≥ 1.0 | 本地持久化，按 workspace 隔离 collection |
| **关系数据库** | SQLite (aiosqlite) | — | 轻量异步，存储 workspace/document/task/message 元数据 |
| **Embedding** | Dashscope text-embedding-v2 | — | 通过 Dashscope SDK 直接调用 |
| **文档解析** | PyMuPDF (PDF), python-docx (DOCX) | — | 结构化解析为章节 |
| **文本分块** | langchain-text-splitters | — | RecursiveCharacterTextSplitter |
| **可观测性** | LangSmith | — | Agent 调用链追踪 |
| **包管理** | uv + hatchling | — | 现代 Python 包管理 |

---

## 三、目录结构

```
backend/
├── langgraph.json          # LangGraph Server 配置（入口、依赖、环境）
├── pyproject.toml           # Python 项目配置 + 依赖声明
├── .env                     # 环境变量（不提交）
├── data/                    # 运行时数据目录（不提交）
│   ├── train_agent.db       #   SQLite 数据库文件
│   ├── chroma/              #   ChromaDB 持久化目录
│   └── files/               #   用户上传文件 + Agent 产出文件
│       └── {workspace_id}/  #     按工作区隔离
│           ├── 原始文件.pdf
│           ├── 原始文件.md   #     解析后的 Markdown 导出
│           └── outputs/     #     Agent 产出物（PPT HTML、口播稿、音频等）
│               └── {ppt_task_id}/  # PPT 产出及其子任务产出
├── skills/                  # Agent 技能目录
│   ├── ppt/                 #   PPT 生成技能
│   │   ├── SKILL.md         #     技能主提示（YAML frontmatter + Markdown）
│   │   ├── assets/          #     静态资源（viewport-base.css）
│   │   └── references/      #     参考文件（style-presets, html-template, animation-patterns）
│   └── narration/           #   口播稿生成技能
│       └── SKILL.md
├── src/                     # 源代码根目录
│   ├── app_context.py       #   统一依赖注入数据类 (AppContext)
│   ├── api/                 #   REST API 层
│   │   ├── routes.py        #     FastAPI 路由定义
│   │   └── deps.py          #     依赖注入（单例初始化）
│   ├── agent/               #   Agent 层
│   │   ├── graph.py         #     LangGraph Agent 图构建
│   │   ├── state.py         #     Agent 状态定义
│   │   ├── prompt_manager.py #    系统提示词
│   │   ├── skill_manager.py #     技能扫描与加载
│   │   └── message_history.py #   消息历史持久化回调 + 中间件
│   ├── middlewares/         #   Agent 中间件
│   │   ├── inject_doc_context.py #  动态注入文档摘要
│   │   ├── summarization.py #     长对话摘要压缩
│   │   ├── model_message_sanitizer.py # 模型请求清洗
│   │   └── logging_middlewares.py #    日志中间件
│   ├── services/            #   业务服务层
│   │   ├── doc_service.py   #     文档上传/解析/分块/摘要编排
│   │   └── tts_service.py   #     TTS 音频生成
│   ├── storage/             #   存储层
│   │   ├── database.py      #     SQLite 封装（异步）
│   │   ├── vector_store.py  #     ChromaDB 封装
│   │   └── file_store.py    #     文件系统封装
│   ├── parsers/             #   文档解析器
│   │   ├── base.py          #     基础数据结构 + 分块逻辑
│   │   ├── pdf_parser.py    #     PDF 解析
│   │   ├── docx_parser.py   #     DOCX 解析
│   │   └── markdown_parser.py #   Markdown/纯文本解析
│   └── tools/               #   Agent 工具
│       ├── rag_search.py    #     知识库检索
│       ├── load_skill.py    #     技能加载
│       ├── save_ppt.py      #     PPT 产出物保存
│       ├── save_narration.py #    口播稿 + TTS 音频保存
│       ├── get_ppt_detail.py #    获取 PPT 任务详情
│       ├── clarify_form.py  #     表单中断收集用户输入
│       ├── run_skill_script.py #  技能脚本执行
│       └── terminal_tool.py #     Shell 命令执行（备用）
└── tests/                   # 单元测试
```

---

## 四、分层架构详解

后端采用 **四层架构**，自上而下依次为：

```
┌──────────────────────────────────────────┐
│  API 层 (routes.py / LangGraph Server)   │  ← 接收外部请求
├──────────────────────────────────────────┤
│  Agent 层 (graph.py + middlewares + tools)│  ← AI 推理与工具调用
├──────────────────────────────────────────┤
│  Service 层 (doc_service + tts_service)  │  ← 业务编排
├──────────────────────────────────────────┤
│  Storage 层 (database / vector / file)   │  ← 数据持久化
└──────────────────────────────────────────┘
```

### 4.1 API 层

**文件**: `src/api/routes.py`, `src/api/deps.py`

#### 4.1.1 FastAPI 服务 (`routes.py`)

提供 RESTful API，所有路由前缀 `/api/`：

| 方法 | 路径 | 功能 | 关键行为 |
|------|------|------|---------|
| `POST` | `/api/workspaces` | 创建工作区 | 同名检测（409），初始化 ext_data |
| `GET` | `/api/workspaces` | 列出用户工作区 | 按 `user_id` 过滤 |
| `GET` | `/api/workspaces/{id}` | 获取工作区详情 | 含 ext_data 配置 |
| `PATCH` | `/api/workspaces/{id}/thread` | 绑定 LangGraph thread_id | 前端持久化会话 |
| `PATCH` | `/api/workspaces/{id}/config` | 更新工作区配置 | ppt_style / voice_id 等 |
| `GET` | `/api/threads/{thread_id}/messages` | 获取聊天消息历史 | turn-based 分页 |
| `DELETE` | `/api/workspaces/{id}` | 删除工作区 | 级联删除文档+向量+文件 |
| `POST` | `/api/workspaces/{id}/documents` | 上传文档 | **异步后台处理** |
| `GET` | `/api/workspaces/{id}/documents` | 列出文档 | 含状态轮询支持 |
| `DELETE` | `/api/workspaces/{id}/documents/{doc_id}` | 删除文档 | 清理文件+向量 |
| `GET` | `/api/workspaces/{id}/tasks` | 列出任务/产出 | 顶层任务+嵌套子任务 |
| `DELETE` | `/api/workspaces/{id}/tasks/{task_id}` | 删除任务 | 级联删除子任务+文件 |
| `PUT` | `/api/workspaces/{id}/tasks/{task_id}/file` | 保存任务文件内容 | PPT HTML 编辑回写 |
| `GET` | `/api/files/{path}` | 下载文件 | 通用文件服务，禁用缓存 |

**关键设计决策**：
- **文档上传采用异步后台处理**：`upload_document` 接口立即返回 `uploaded` 状态，解析/分块/索引/摘要在 `BackgroundTasks` 中异步执行
- **父子任务层级**：`list_tasks` 仅返回顶层任务（PPT），子任务（口播稿、音频）通过 `children` 字段嵌套返回
- **任务文件回写**：`save_task_file` 支持 PPT HTML 的在线编辑保存
- **CORS 全开放**：开发阶段 `allow_origins=["*"]`
- **静态资源挂载**：PPT 技能的资产和模板通过 `StaticFiles` 挂载到 `/ppt-assets` 和 `/ppt-templates`

#### 4.1.2 依赖注入 (`deps.py`)

通过 `AppContext.from_env()` 创建统一上下文，再暴露向后兼容的单例：

```python
app_ctx = AppContext.from_env()
db = app_ctx.db
vector_store = app_ctx.vector_store
file_store = app_ctx.file_store
skill_manager = app_ctx.skill_manager
llm = ChatOpenAI(...)  # 用于文档摘要生成（SUMMARIZATION_MODEL）
doc_service = DocService(db=db, vector_store=vector_store, file_store=file_store, llm=llm)
```

> 注意：FastAPI 进程使用 `deps.py` 的实例，LangGraph 进程在 `graph.py._make_default_graph()` 中独立创建自己的实例。

---

### 4.2 Agent 层

**文件**: `src/agent/graph.py`, `src/agent/state.py`, `src/agent/prompt_manager.py`, `src/agent/skill_manager.py`, `src/agent/message_history.py`

这是 Train Agent 的核心智能层，基于 **LangChain Agent + LangGraph** 构建。

#### 4.2.1 Agent 图 (`graph.py`)

使用 `langchain.agents.create_agent()` 创建标准的 ReAct Agent：

```
用户消息 → [中间件链] → LLM 推理 → 工具调用 → LLM 继续推理 → 最终回复
                              ↑                ↓
                         middlewares/*    tools/*
```

**核心组件**：

- **Model**: `ChatOpenAI`，通过 OpenAI 兼容接口调用 DeepSeek（`MAIN_MODEL`），开启 `streaming` 和 `enable_thinking`
- **State**: `TrainAgentState`，继承 `AgentState`，扩展 workspace/config 字段
- **Tools**: 7 个注册工具（见 4.3 节）
- **Middlewares**: 见 4.2.5 节

#### 4.2.2 Agent 状态 (`state.py`)

```python
class TrainAgentState(AgentState):
    workspace_id: str           # 当前工作区 ID
    ppt_style: str              # PPT 风格（如 "swiss-modern"）
    voice_id: str               # TTS 音色 ID（如 "Cherry"）
    current_ppt_task_id: str    # 当前 PPT 任务 ID（口播稿生成时使用）
```

`workspace_id` 贯穿整个 Agent 调用链，工具通过 `runtime.state.get("workspace_id")` 获取。`ppt_style` 和 `voice_id` 由前端通过 workspace 配置传入，工具读取后用于产出定制化的 PPT 和音频。

#### 4.2.3 系统提示词 (`prompt_manager.py`)

定义 Agent 的角色为 **企业培训专家**，核心约束包括：
- 结构化 Markdown 输出
- 基于文档事实，禁止捏造
- 引用规范（`{{ref:文档名|章节}}`）
- 技能使用（`/ppt`、`/narrate` 命令触发）
- 场景限定（仅处理培训相关请求）
- 动态注入当前 PPT 产出元信息（含 topic/summary）

运行时通过 `inject_doc_context` 中间件动态追加文档摘要。

#### 4.2.4 技能管理器 (`skill_manager.py`)

实现 **LangChain Skills 模式（渐进式披露）**：

```
skills/
├── ppt/
│   ├── SKILL.md              ← YAML frontmatter (name + description)
│   ├── assets/               ← viewport-base.css
│   └── references/           ← style-presets, html-template, animation-patterns
└── narration/
    └── SKILL.md              ← 口播稿生成技能
```

- **启动时扫描** `skills/` 目录，解析所有 `SKILL.md` 的 YAML frontmatter，提取 `name` + `description`
- **Agent 仅看到名称和描述**（通过 `load_skill` 工具的 docstring 注入）
- **按需加载**：Agent 调用 `load_skill(skill_name)` 时才读取完整技能内容
- **文件加载**：支持 `load_skill(skill_name, file_paths=[...])` 批量加载技能目录下的关联文件
- **安全约束**：`load_file()` 通过路径校验防止目录逃逸

#### 4.2.5 中间件 (`middlewares/`)

中间件按执行顺序注册，覆盖 Agent 生命周期各阶段：

| 中间件 | 阶段 | 职责 |
|--------|------|------|
| `log_before_agent` | before_agent | 记录 Agent 开始执行日志 |
| `MessageHistoryMiddleware` | before/after_agent | 持久化消息历史到 SQLite |
| `log_before_model` | before_model | 记录模型请求前日志 |
| `sanitize_model_request` | before_model | 清洗模型请求（移除无效字段） |
| `inject_doc_context` | before_model | 动态注入当前 workspace 的文档摘要 |
| `log_after_model` | after_model | 记录模型响应日志 |
| `log_after_agent` | after_agent | 记录 Agent 完成日志 |
| `TrainAgentSummarizationMiddleware` | after_agent | 长对话摘要压缩（token 超 20000 时触发） |

**消息历史持久化**：
- `MessageHistoryCallback` 将每条消息（human/ai/tool）写入 `message` 表
- 自动过滤摘要生成的中间消息（`lc_source=summarization`）
- 通过 `MessageHistoryMiddleware` 在 Agent 执行前后触发

**长对话摘要**：
- `TrainAgentSummarizationMiddleware` 监控消息 token 总量
- 超过阈值（20000 tokens）时，保留最近 8 条消息，将更早的消息压缩为摘要
- 使用独立的 LLM 实例生成摘要（`MAIN_MODEL`）

---

### 4.3 工具层 (Tools)

Agent 注册了 **7 个工具**：

#### 4.3.1 `rag_search` — 知识库检索

- **触发时机**：用户提出与文档内容相关的问题
- **实现**：调用 `VectorStore.search()`，在当前 workspace 的 ChromaDB collection 中做余弦相似度检索
- **输出格式**：带结构化位置信息的检索片段（文件名 | 章节 > 小节 | 页码）
- **workspace 隔离**：通过 `runtime.state["workspace_id"]` 自动定位 collection

#### 4.3.2 `load_skill` — 技能加载

- **触发时机**：用户使用 `/ppt`、`/narrate` 等命令，或 Agent 判断需要特定技能
- **两种调用模式**：
  - 不带 `file_paths`：返回技能主提示 + `linked_files` 列表
  - 带 `file_paths`：批量加载技能目录下的文件（最多 5 个）
- **动态 docstring**：工具描述中列出所有可用技能的名称和描述

#### 4.3.3 `save_ppt` — PPT 产出物保存

- **触发时机**：Agent 完成 PPT 生成后
- **流程**：创建 Task 记录（type=ppt）→ 保存 HTML 文件到 `files/{workspace_id}/outputs/{ppt_task_id}/` → 更新 Task 状态为 completed
- **前端联动**：保存后前端通过轮询 Task 列表自动展示新产出

#### 4.3.4 `save_narration` — 口播稿 + TTS 音频保存

- **触发时机**：Agent 完成口播稿生成后
- **流程**：创建 Task 记录（type=narration, parent_task_id=ppt_task_id）→ 保存口播稿文本 → 逐页生成 TTS 音频 → 更新 Task 状态
- **TTS 调用**：通过 `TTSService` 调用 Dashscope qwen3-tts-flash
- **文件命名**：`{narration_task_id}_narration.md`（文本），`{narration_task_id}_{slide_number}.wav`（音频）

#### 4.3.5 `get_ppt_detail` — 获取 PPT 任务详情

- **触发时机**：Agent 需要了解已有 PPT 的结构信息（如幻灯片数量、大纲等）
- **实现**：从 DB 读取 PPT 任务的 result_data

#### 4.3.6 `clarify_form` — 表单中断

- **触发时机**：Agent 需要用户澄清意图或提供参数
- **实现**：使用 LangGraph 的 `interrupt()` 机制暂停 Agent 执行，发送表单定义到前端
- **表单字段类型**：`text`、`select`、`multiselect`
- **恢复**：前端提交表单后通过 LangGraph `resume` API 恢复 Agent 执行

#### 4.3.7 `run_skill_script` — 技能脚本执行

- **触发时机**：技能中定义的辅助脚本需要执行
- **安全措施**：workdir 必须是绝对路径，校验 shell 元字符，支持超时和后台执行

---

### 4.4 Service 层

#### 4.4.1 DocService (`doc_service.py`)

`DocService` 是文档处理的业务编排器，协调解析器、存储层和 LLM：

#### 文档处理流水线

```
上传文件 (bytes)
    │
    ▼
┌─ create_document_upload ─────────────────────────┐
│  1. 检测文件类型 (pdf/docx/markdown/text)         │
│  2. FileStore.save() → 保存原始文件                │
│  3. Database.create_document() → 创建元数据记录    │
│  4. 返回 status="uploaded"                        │
└──────────────────────────────────────────────────┘
    │ (BackgroundTasks 异步执行)
    ▼
┌─ process_document ───────────────────────────────┐
│  ① status="parsing"                              │
│     → 结构化解析为 DocumentSection 列表            │
│     → 导出 Markdown 文件                          │
│                                                  │
│  ② status="parsed" → "chunking"                  │
│     → split_sections_into_chunks()               │
│     → RecursiveCharacterTextSplitter             │
│     → 生成 ChunkWithMetadata 列表                 │
│                                                  │
│  ③ status="indexing"                             │
│     → VectorStore.add_structured_chunks()        │
│     → 写入 ChromaDB（按 workspace 隔离 collection）│
│                                                  │
│  ④ status="summarizing"                          │
│     → LLM 生成 200 字摘要（失败则截断 fallback）   │
│                                                  │
│  ⑤ status="ready"                                │
│     → 文档就绪，可供 RAG 检索                      │
└──────────────────────────────────────────────────┘
```

**状态机**：`uploaded → parsing → parsed → chunking → indexing → summarizing → ready`（任意阶段失败进入 `error`）

**删除操作**：
- `delete_document()`：删除文件 + 解析的 Markdown + 向量数据 + DB 记录
- `delete_workspace()`：遍历所有文档执行删除 + 删除 collection + 删除文件目录

#### 4.4.2 TTSService (`tts_service.py`)

`TTSService` 封装 Dashscope TTS 调用，用于口播稿音频生成：

- **模型**：qwen3-tts-flash
- **调用模式**：非流式，逐页合成
- **输入**：口播稿文本 + 音色 ID
- **输出**：WAV 音频文件保存到 `outputs/{ppt_task_id}/` 目录

---

### 4.5 Storage 层

#### 4.5.1 Database (`database.py`)

- **引擎**：aiosqlite（异步 SQLite）
- **四张表**：
  - `workspace(id, user_id, name, thread_id, ext_data, created_at)` — 工作区，`ext_data` 存储 JSON 配置（ppt_style, voice_id）
  - `document(id, workspace_id, filename, file_type, summary, storage_path, status, error_message, created_at, updated_at)` — 文档
  - `task(id, workspace_id, type, title, status, result_data, parent_task_id, created_at, updated_at)` — 任务/产出，支持父子层级
  - `message(id, thread_id, workspace_id, message_id, role, type, content, tool_calls, tool_call_id, name, additional_kwargs, response_metadata, created_at, updated_at)` — 聊天消息历史
- **外键**：document/task → workspace（ON DELETE CASCADE），task.parent_task_id → task（ON DELETE SET NULL）
- **自动迁移**：`_migrate_tables()` 处理新增列的兼容

**消息历史查询**：
- `list_thread_messages()` 实现 turn-based 分页：以 human 消息为 turn 边界，`limit` 控制 turn 数量，`before` 支持游标翻页
- 返回 `{messages: [...], next_cursor: id | null}`

**任务层级查询**：
- `list_tasks()` 仅返回顶层任务（`parent_task_id IS NULL`），子任务通过 `children` 字段嵌套
- `delete_task()` 对 PPT 类型任务级联删除所有子任务

#### 4.5.2 VectorStore (`vector_store.py`)

- **引擎**：ChromaDB PersistentClient
- **Embedding**：`DashscopeEmbeddingFunction`，封装 Dashscope text-embedding-v2 SDK
- **Collection 策略**：每个 workspace 一个 collection，名称为 `ws_{workspace_id}`
- **元数据**：每个 chunk 携带 `doc_id, filename, chunk_index, section_title, chapter_title, page_start, page_end, section_level`
- **检索**：余弦相似度（`hnsw:space=cosine`），支持按 `doc_id` 过滤
- **批量写入**：默认 batch_size=20

#### 4.5.3 FileStore (`file_store.py`)

- **存储结构**：`{base_dir}/{workspace_id}/{filename}`
- **功能**：同步/异步写入、单文件删除、整个 workspace 目录删除
- **产出路径**：`{workspace_id}/outputs/{ppt_task_id}/`（PPT 及其子任务产出统一存放在 PPT 任务目录下）

---

### 4.6 解析器层 (Parsers)

#### 基础数据结构 (`base.py`)

- **`DocumentSection`**：解析产出的结构化单元（title, level, content, page_start/end, parent_title）
- **`ChunkWithMetadata`**：向量存储的 chunk 单元，携带章节/页码元数据
- **`split_sections_into_chunks()`**：使用 `RecursiveCharacterTextSplitter`，chunk_size=2000，overlap=200

#### 解析器实现

| 解析器 | 文件类型 | 库 | 结构化能力 |
|--------|---------|-----|-----------|
| `PdfParser` | .pdf | PyMuPDF | 按页解析，识别标题层级 |
| `DocxParser` | .docx/.doc | python-docx | 按段落解析，利用 Word 标题样式 |
| `MarkdownParser` | .md/.txt | 内置 | 按标题层级拆分 |

---

## 五、核心数据流

### 5.1 文档上传与索引

```
前端 → POST /api/workspaces/{id}/documents (multipart file)
  → routes.py: 读取文件内容
  → doc_service.create_document_upload(): 保存文件 + 创建 DB 记录
  → BackgroundTasks: doc_service.process_document()
    → Parser: 结构化解析
    → Splitter: 分块
    → VectorStore: 写入向量
    → LLM: 生成摘要
    → Database: 更新状态为 ready
前端 ← 轮询 GET /api/workspaces/{id}/documents 追踪状态
```

### 5.2 智能问答

```
前端 → LangGraph Stream API (:2024) 发送消息 + workspace_id + ppt_style + voice_id
  → graph.py: 中间件链处理
    → MessageHistoryMiddleware: 持久化消息
    → sanitize_model_request: 清洗请求
    → inject_doc_context: 注入文档摘要
  → LLM 推理 → 决定调用 rag_search
  → rag_search: ChromaDB 检索 → 返回带位置信息的片段
  → LLM 基于检索结果生成带引用标记的回答
  → TrainAgentSummarizationMiddleware: 检查是否需要摘要压缩
前端 ← 流式接收 AI 回复
```

### 5.3 PPT 生成

```
前端 → 用户发送 "/ppt 新员工培训"
  → LLM 识别 /ppt 命令 → 调用 load_skill("html-ppt")
  → 获取 PPT 技能完整提示 + linked_files 列表
  → (可选) 调用 clarify_form → 前端展示表单 → 用户填写 → resume
  → (可选) 调用 rag_search 检索相关文档
  → (可选) 调用 load_skill("html-ppt", file_paths=[...]) 加载参考文件
  → LLM 生成完整 PPT HTML
  → 调用 save_ppt(type="ppt", title=..., content=HTML, ppt_style=...)
    → 创建 Task + 保存文件到 outputs/{task_id}/
前端 ← 产出面板展示新 PPT，可预览、编辑和下载
```

### 5.4 口播稿生成

```
前端 → 用户在 PPT 任务菜单中点击"生成口播稿"
  → workspace page 设置 current_ppt_task_id + 发送 /narrate 命令
  → LLM 识别 /narrate 命令 → 调用 load_skill("narration")
  → Agent 检查 current_ppt_task_id，获取 PPT 大纲
  → (可选) 调用 rag_search 检索文档增强内容
  → LLM 生成逐页口播稿文本
  → 调用 save_narration(ppt_task_id=..., content=..., voice_id=...)
    → 创建子 Task (parent_task_id=ppt_task_id)
    → 保存口播稿文本文件
    → 逐页调用 TTSService 生成音频
    → 更新 Task 状态为 completed
前端 ← 产出面板在 PPT 下方展示口播稿子任务，可播放
```

### 5.5 消息历史恢复

```
前端 → 打开工作区聊天面板
  → 检查 workspace.thread_id
  → 如有 thread_id → GET /api/threads/{thread_id}/messages
    → 返回按 turn 分组的消息列表 + next_cursor
  → 前端加载历史消息渲染到 Thread 组件
  → 用户滚动到顶部 → 使用 next_cursor 加载更多
  → useStream 接管后续实时通信
```

---

## 六、配置与环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | 必填 | DeepSeek API 密钥 |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `MAIN_MODEL` | `deepseek-v4-flash` | Agent 图使用的 LLM 模型 |
| `SUMMARIZATION_API_KEY` | — | 摘要生成 API 密钥 |
| `SUMMARIZATION_API_BASE` | `https://api.deepseek.com` | 摘要生成 API 地址 |
| `SUMMARIZATION_MODEL` | `deepseek-v4-flash` | 摘要/文档处理用 LLM |
| `EMBEDDING_API_KEY` | 必填 | Embedding API 密钥 |
| `EMBEDDING_API_BASE` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Embedding API 地址 |
| `EMBEDDING_MODEL` | `text-embedding-v2` | Embedding 模型名 |
| `TTS_API_KEY` | 必填 | TTS API 密钥 |
| `TTS_API_BASE` | Dashscope 多模态接口 | TTS API 地址 |
| `TTS_MODEL` | `qwen3-tts-flash` | TTS 模型名 |
| `DATA_DIR` | `./data` | 数据存储根目录 |
| `LANGSMITH_TRACING` | `true` | 是否启用 LangSmith 追踪 |
| `LANGSMITH_API_KEY` | — | LangSmith API 密钥 |

**LangGraph Server 配置** (`langgraph.json`)：
```json
{
  "python_version": "3.12",
  "dependencies": ["."],
  "graphs": {
    "train_agent": "src.agent.graph:graph"
  },
  "env": ".env"
}
```

---

## 七、关键设计决策

1. **双进程架构**：FastAPI 处理 CRUD 和文件操作，LangGraph 专注 Agent 流式推理，职责分离
2. **AppContext 统一入口**：所有存储实例通过 `AppContext` 数据类捆绑，两个进程各自创建独立实例
3. **Workspace 隔离**：所有数据（文件、向量、元数据）以 workspace_id 为维度隔离
4. **异步文档处理**：上传立即返回，后台异步完成解析→分块→索引→摘要的流水线
5. **渐进式技能披露**：Agent 启动时只看到技能名称和描述，按需加载完整技能内容，减少 token 消耗
6. **父子任务层级**：PPT 任务为顶层任务，口播稿/音频任务通过 `parent_task_id` 挂载，支持级联删除
7. **消息历史持久化**：所有对话消息独立存储在 SQLite 的 message 表中，支持 turn-based 分页和恢复
8. **长对话摘要压缩**：超过 token 阈值时自动压缩历史消息为摘要，保持 Agent 上下文窗口可控
9. **中断式交互**：`clarify_form` 利用 LangGraph interrupt 机制实现 Agent-用户的多轮表单交互
10. **动态提示注入**：每次 Agent 推理前，中间件自动注入当前 workspace 的文档摘要和 PPT 产出元信息
11. **ExternalCommand 机制**：前端通过 slash command 胶囊 UI 触发复杂技能（如 /narrate），降低用户输入门槛