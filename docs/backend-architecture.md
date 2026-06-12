# Train Agent 后端架构设计文档

> 本文档面向 AI 及开发者，旨在帮助快速理解 Train Agent 后端的整体设计、模块职责与数据流转。

---

## 一、系统总览

Train Agent 后端由 **两个独立进程** 组成，共享同一份代码库：

| 进程 | 框架 | 端口 | 职责 |
|------|------|-----:|------|
| **FastAPI 服务** | FastAPI + Uvicorn | 8000 | REST API：工作区/文档/任务 CRUD、文件上传与下载 |
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
                          │                       │  tools/*         │
                          │                       └────────┬─────────┘
                          │                                │
                          ▼                                ▼
                 ┌─────────────────────────────────────────────────┐
                 │              共享存储层                           │
                 │                                                 │
                 │  SQLite (database.py)   ← 元数据: workspace,    │
                 │                            document, task       │
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
| **LLM 接入** | langchain-openai + Dashscope | — | 通过 OpenAI 兼容接口调用通义千问系列 |
| **向量数据库** | ChromaDB | ≥ 1.0 | 本地持久化，按 workspace 隔离 collection |
| **关系数据库** | SQLite (aiosqlite) | — | 轻量异步，存储 workspace/document/task 元数据 |
| **Embedding** | Dashscope text-embedding-v2 | — | 通过 Dashscope SDK 直接调用 |
| **文档解析** | PyMuPDF (PDF), python-docx (DOCX) | — | 结构化解析为章节 |
| **文本分块** | langchain-text-splitters | — | RecursiveCharacterTextSplitter |
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
│           └── outputs/     #     Agent 产出物（PPT HTML 等）
├── skills/                  # Agent 技能目录
│   └── ppt/                 #   PPT 生成技能
│       ├── SKILL.md         #     技能主提示（YAML frontmatter + Markdown）
│       ├── SKILL.zh-CN.md   #     中文版
│       ├── STYLE_PRESETS.md #     样式预设参考
│       ├── html-template.md #     HTML 模板参考
│       ├── animation-patterns.md  # 动画模式参考
│       ├── viewport-base.css      # 基础 CSS
│       └── scripts/         #     辅助脚本
├── static/                  # 静态资源（PPT 资产/模板）
├── src/                     # 源代码根目录
│   ├── api/                 #   REST API 层
│   │   ├── routes.py        #     FastAPI 路由定义
│   │   └── deps.py          #     依赖注入（单例初始化）
│   ├── agent/               #   Agent 层
│   │   ├── graph.py         #     LangGraph Agent 图构建
│   │   ├── state.py         #     Agent 状态定义
│   │   ├── prompt_manager.py #    系统提示词
│   │   └── skill_manager.py #     技能扫描与加载
│   ├── services/            #   业务服务层
│   │   └── doc_service.py   #     文档上传/解析/分块/摘要编排
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
│       ├── save_output.py   #     产出物保存
│       ├── clarify_form.py  #     表单中断收集用户输入
│       └── terminal_tool.py #     Shell 命令执行
└── tests/                   # 单元测试
```

---

## 四、分层架构详解

后端采用 **四层架构**，自上而下依次为：

```
┌──────────────────────────────────────────┐
│  API 层 (routes.py / LangGraph Server)   │  ← 接收外部请求
├──────────────────────────────────────────┤
│  Agent 层 (graph.py + tools/*)           │  ← AI 推理与工具调用
├──────────────────────────────────────────┤
│  Service 层 (doc_service.py)             │  ← 业务编排
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
| `POST` | `/api/workspaces` | 创建工作区 | 同名检测（409） |
| `GET` | `/api/workspaces` | 列出用户工作区 | 按 `user_id` 过滤 |
| `GET` | `/api/workspaces/{id}` | 获取工作区详情 | 404 处理 |
| `PATCH` | `/api/workspaces/{id}/thread` | 绑定 LangGraph thread_id | 前端持久化会话 |
| `DELETE` | `/api/workspaces/{id}` | 删除工作区 | 级联删除文档+向量+文件 |
| `POST` | `/api/workspaces/{id}/documents` | 上传文档 | **异步后台处理** |
| `GET` | `/api/workspaces/{id}/documents` | 列出文档 | 含状态轮询支持 |
| `DELETE` | `/api/workspaces/{id}/documents/{doc_id}` | 删除文档 | 清理文件+向量 |
| `GET` | `/api/workspaces/{id}/tasks` | 列出任务/产出 | — |
| `DELETE` | `/api/workspaces/{id}/tasks/{task_id}` | 删除任务 | — |
| `GET` | `/api/files/{path}` | 下载文件 | 通用文件服务 |

**关键设计决策**：
- **文档上传采用异步后台处理**：`upload_document` 接口立即返回 `uploaded` 状态，解析/分块/索引/摘要在 `BackgroundTasks` 中异步执行，前端通过轮询 `list_documents` 追踪状态变化
- **CORS 全开放**：开发阶段 `allow_origins=["*"]`
- **静态资源挂载**：PPT 技能的资产和模板通过 `StaticFiles` 挂载到 `/ppt-assets` 和 `/ppt-templates`

#### 4.1.2 依赖注入 (`deps.py`)

模块级单例初始化，所有存储和服务实例在导入时创建：

```python
db = Database(f"{DATA_DIR}/train_agent.db")
vector_store = VectorStore(f"{DATA_DIR}/chroma")
file_store = FileStore(f"{DATA_DIR}/files")
llm = ChatOpenAI(...)  # 用于文档摘要生成
doc_service = DocService(db=db, vector_store=vector_store, file_store=file_store, llm=llm)
skill_manager = SkillManager("../skills")
```

> 注意：FastAPI 进程使用 `deps.py` 的实例，LangGraph 进程在 `graph.py._make_default_graph()` 中独立创建自己的实例。

---

### 4.2 Agent 层

**文件**: `src/agent/graph.py`, `src/agent/state.py`, `src/agent/prompt_manager.py`, `src/agent/skill_manager.py`

这是 Train Agent 的核心智能层，基于 **LangChain Agent + LangGraph** 构建。

#### 4.2.1 Agent 图 (`graph.py`)

使用 `langchain.agents.create_agent()` 创建标准的 ReAct Agent：

```
用户消息 → [inject_doc_context 中间件] → LLM 推理 → 工具调用 → LLM 继续推理 → 最终回复
                                          ↑                ↓
                                     patch_tool_call_ids   rag_search / load_skill /
                                       中间件               save_output / clarify_form
```

**核心组件**：

- **Model**: `ChatOpenAI`，通过 OpenAI 兼容接口调用通义千问（`qwen3-plus`），开启 `streaming` 和 `enable_thinking`
- **State**: `TrainAgentState`，继承 `AgentState`，扩展 `workspace_id` 字段
- **Tools**: 4 个注册工具（见 4.3 节）
- **Middleware**:
  - `inject_doc_context`（`@dynamic_prompt`）：每次推理前，从 DB 读取当前 workspace 的文档摘要，注入到系统提示词中
  - `patch_tool_call_ids`（`@wrap_model_call`）：修复 LLM 返回的空 tool_call id 问题

#### 4.2.2 Agent 状态 (`state.py`)

```python
class TrainAgentState(AgentState):
    workspace_id: str  # 当前工作区 ID，由前端在 stream 请求时传入
```

`workspace_id` 贯穿整个 Agent 调用链，工具通过 `runtime.state.get("workspace_id")` 获取，实现 **workspace 级别的数据隔离**。

#### 4.2.3 系统提示词 (`prompt_manager.py`)

定义 Agent 的角色为 **企业培训专家**，核心约束包括：
- 结构化 Markdown 输出
- 基于文档事实，禁止捏造
- 引用规范（`{{ref:文档名|章节}}`）
- 技能使用（`/ppt` 命令触发）
- 场景限定（仅处理培训相关请求）

运行时通过 `inject_doc_context` 中间件动态追加文档摘要。

#### 4.2.4 技能管理器 (`skill_manager.py`)

实现 **LangChain Skills 模式（渐进式披露）**：

```
skills/
└── ppt/
    ├── SKILL.md              ← YAML frontmatter (name + description)
    ├── references/           ← 按需加载的参考文件
    ├── scripts/              ← 辅助脚本
    └── assets/               ← 静态资源
```

- **启动时扫描** `skills/` 目录，解析所有 `SKILL.md` 的 YAML frontmatter，提取 `name` + `description`
- **Agent 仅看到名称和描述**（通过 `load_skill` 工具的 docstring 注入）
- **按需加载**：Agent 调用 `load_skill(skill_name)` 时才读取完整技能内容
- **文件加载**：支持 `load_skill(skill_name, file_paths=[...])` 批量加载技能目录下的关联文件
- **安全约束**：`load_file()` 通过路径校验防止目录逃逸

---

### 4.3 工具层 (Tools)

Agent 注册了 **5 个工具**（其中 4 个在 Agent 图中注册，1 个备用）：

#### 4.3.1 `rag_search` — 知识库检索

- **触发时机**：用户提出与文档内容相关的问题
- **实现**：调用 `VectorStore.search()`，在当前 workspace 的 ChromaDB collection 中做余弦相似度检索
- **输出格式**：带结构化位置信息的检索片段（文件名 | 章节 > 小节 | 页码）
- **workspace 隔离**：通过 `runtime.state["workspace_id"]` 自动定位 collection

#### 4.3.2 `load_skill` — 技能加载

- **触发时机**：用户使用 `/ppt` 等命令，或 Agent 判断需要特定技能
- **两种调用模式**：
  - 不带 `file_paths`：返回技能主提示 + `linked_files` 列表
  - 带 `file_paths`：批量加载技能目录下的文件（最多 5 个）
- **动态 docstring**：工具描述中列出所有可用技能的名称和描述

#### 4.3.3 `save_output` — 产出物保存

- **触发时机**：Agent 完成 PPT/报告等产出后
- **流程**：创建 Task 记录 → 保存文件到 `files/{workspace_id}/outputs/` → 更新 Task 状态
- **产出类型**：`ppt`（保存为 .html）、`report`（保存为 .md）
- **前端联动**：保存后前端通过轮询 Task 列表自动展示新产出

#### 4.3.4 `clarify_form` — 表单中断

- **触发时机**：Agent 需要用户澄清意图或提供参数
- **实现**：使用 LangGraph 的 `interrupt()` 机制暂停 Agent 执行，发送表单定义到前端
- **表单字段类型**：`text`、`select`、`multiselect`
- **恢复**：前端提交表单后通过 LangGraph `resume` API 恢复 Agent 执行

#### 4.3.5 `terminal` — Shell 命令执行（备用）

- **触发时机**：技能脚本执行等场景
- **安全措施**：workdir 必须是绝对路径，校验 shell 元字符，支持超时和后台执行
- **注意**：当前未在 Agent 图中注册，作为预留能力

---

### 4.4 Service 层

**文件**: `src/services/doc_service.py`

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
│  ② status="chunking"                             │
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

---

### 4.5 Storage 层

#### 4.5.1 Database (`database.py`)

- **引擎**：aiosqlite（异步 SQLite）
- **三张表**：
  - `workspace(id, user_id, name, thread_id, created_at)` — 工作区
  - `document(id, workspace_id, filename, file_type, summary, storage_path, status, error_message, created_at, updated_at)` — 文档
  - `task(id, workspace_id, type, title, status, result_data, created_at, updated_at)` — 任务/产出
- **外键**：document/task → workspace（ON DELETE CASCADE）
- **自动迁移**：`_migrate_tables()` 处理新增列的兼容

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
- **产出路径**：`{workspace_id}/outputs/{filename}`

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
前端 → LangGraph Stream API (:2024) 发送消息 + workspace_id
  → graph.py: inject_doc_context 中间件注入文档摘要
  → LLM 推理 → 决定调用 rag_search
  → rag_search: ChromaDB 检索 → 返回带位置信息的片段
  → LLM 基于检索结果生成带引用标记的回答
前端 ← 流式接收 AI 回复
```

### 5.3 PPT 生成

```
前端 → 用户发送 "/ppt 新员工培训"
  → LLM 识别 /ppt 命令 → 调用 load_skill("ppt")
  → 获取 PPT 技能完整提示 + linked_files 列表
  → (可选) 调用 clarify_form → 前端展示表单 → 用户填写 → resume
  → (可选) 调用 rag_search 检索相关文档
  → (可选) 调用 load_skill("ppt", file_paths=[...]) 加载参考文件
  → LLM 生成完整 PPT HTML
  → 调用 save_output(type="ppt", title=..., content=HTML)
    → 创建 Task + 保存文件
前端 ← 产出面板展示新 PPT，可预览和下载
```

---

## 六、配置与环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DASHSCOPE_API_KEY` | 必填 | 通义千问 API 密钥 |
| `OPENAI_API_BASE` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI 兼容 API 地址 |
| `OPENAI_API_KEY` | — | 同 DASHSCOPE_API_KEY（LangGraph 进程使用） |
| `LLM_MODEL` | `qwen-plus`（API）/ `qwen3-plus`（Agent） | LLM 模型名 |
| `EMBEDDING_MODEL` | `text-embedding-v2` | Embedding 模型名 |
| `DATA_DIR` | `./data` | 数据存储根目录 |

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
2. **Workspace 隔离**：所有数据（文件、向量、元数据）以 workspace_id 为维度隔离
3. **异步文档处理**：上传立即返回，后台异步完成解析→分块→索引→摘要的流水线
4. **渐进式技能披露**：Agent 启动时只看到技能名称和描述，按需加载完整技能内容，减少 token 消耗
5. **结构化解析**：保留文档的章节层级、页码信息，使 RAG 检索结果可精确定位来源
6. **中断式交互**：`clarify_form` 利用 LangGraph interrupt 机制实现 Agent-用户的多轮表单交互
7. **动态提示注入**：每次 Agent 推理前，中间件自动注入当前 workspace 的文档摘要，无需用户手动提供上下文
