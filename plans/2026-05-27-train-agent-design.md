# 培训 Agent 设计文档

## 目标

构建一个培训垂直场景的 Agent 产品，基于通用 Agent 架构（Context Manager / Tool Manager / Skill Manager），通过特定 System Prompt、Tools、Skills 定位于培训场景。MVP 实现：知识库多轮对话 + PPT 生成。

## 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js + @langchain/react + assistant-ui)               │
│  ┌──────────┐  ┌─────────────────────┐  ┌────────────────────────┐ │
│  │Workspace │  │   Chat Panel        │  │   Task Panel           │ │
│  │  Page    │  │ (streaming + forms) │  │  (产出管理)             │ │
│  └──────────┘  └─────────────────────┘  └────────────────────────┘ │
│                ┌─────────────────────┐                              │
│                │   Doc Panel (左侧)   │                              │
│                └─────────────────────┘                              │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ SSE (LangGraph Protocol)
┌─────────────────────────────▼───────────────────────────────────────┐
│  Backend: LangGraph Python Server (langgraph serve)                  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Agent Runtime (ReAct)                        │ │
│  │  context_mgr.build() → LLM → parse_action → tool_mgr → loop   │ │
│  └────────┬──────────┬───────────┬──────────┬────────────────────┘ │
│           │          │           │          │                        │
│  ┌────────▼──┐ ┌─────▼────┐ ┌───▼────┐ ┌───▼──────────┐           │
│  │ Context   │ │  Tool    │ │ Skill  │ │   Prompt     │           │
│  │ Manager   │ │ Manager  │ │Manager │ │  Manager     │           │
│  └───────────┘ └──────────┘ └────────┘ └──────────────┘           │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Service Layer                                │ │
│  │  WorkspaceService  │  DocService  │  TaskService (产出管理)     │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Storage Layer                                │ │
│  │  SQLite (结构化)  │  ChromaDB (向量, per-workspace collection) │ │
│  │                   │  FileStorage (原文件+产出物)                │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

## 数据模型

```sql
CREATE TABLE workspace (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspace(id),
    filename TEXT NOT NULL,
    file_type TEXT,              -- pdf/docx/md/url
    summary TEXT,               -- LLM 生成的摘要（Context Layer 1）
    storage_path TEXT,          -- 原文件路径
    status TEXT DEFAULT 'processing', -- processing/ready/error
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE task (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspace(id),
    type TEXT NOT NULL,          -- ppt/report/...
    title TEXT,
    status TEXT DEFAULT 'generating', -- generating/completed/failed
    result_data TEXT,            -- JSON: 文件路径、预览URL等
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**ChromaDB**: 每个 workspace 一个 collection (`ws_{workspace_id}`)，每个 chunk metadata 携带 `doc_id`，支持按文档过滤检索。

## Context Manager 分层

| Layer | 内容 | 可裁剪 |
|-------|------|--------|
| L0 | System Prompt（角色+拒绝非培训场景） | ❌ |
| L1 | 当前 workspace 所有文档摘要 | ❌ |
| L2 | 当前轮用户输入 + RAG 检索片段 | ❌ |
| L3 | 近期对话历史（70% token 时压缩） | ✅ |

压缩策略：L3 中较早消息被 LLM 摘要替换。

## Tools

| Tool | 功能 |
|------|------|
| `clarify_form` | 向前端推送表单，收集用户澄清信息 |
| `rag_search` | 基于 ChromaDB 检索文档片段（内部直接调用 vector store） |
| `load_skill` | 加载专业技能 prompt（docstring 中列出可用 skill 名称+描述，progressive disclosure） |
| `save_output` | 保存 Skill 产出物（文件存储 + Task 记录），产出出现在用户产出面板 |
| `web_search` | 联网搜索 |

## Skills（LangChain Skills Pattern）

参考：[LangChain Skills 文档](https://docs.langchain.com/oss/python/langchain/multi-agent/skills)

**核心原则：Agent 不感知任何 Skill 业务逻辑。**

Skills = prompt-driven specialization。每个 Skill 是一个 `SKILL.md` 文件（含 YAML frontmatter: name + description），存放在 `backend/skills/<name>/SKILL.md`。

**执行机制：**
1. `SkillManager` 启动时扫描 `skills/` 目录，解析所有 SKILL.md 的 frontmatter
2. `load_skill` tool 的 docstring 动态包含所有可用 skill 的 name + description（progressive disclosure）
3. Agent 通过 tool schema 看到可用 skill 列表，按需调用 `load_skill(skill_name="xxx")` 加载完整内容
4. 加载后 SKILL.md 内容作为 tool result 返回，Agent 按其中的指引执行
5. Skill 执行在主 Agent ReAct loop 中**同步进行，流式可见**
6. 产出物写入 Task 记录归档

**MVP Skills：**

| Skill | 触发 | 产出 |
|-------|------|------|
| `ppt` | `/ppt` 命令 或 Agent 判断适用 | HTML 演示文稿文件 |

PPT Skill 参考 `/Users/whr/workspace/projects/frontend-slides` 的生成能力。

**扩展新 Skill = 新增一个 `skills/<name>/SKILL.md` 文件，零代码改动。**

## 任务模块（产出管理）

定位：**产出归档 + 状态追踪**。Agent 对话中产生的产出物统一记录在此。

| 状态 | 含义 |
|------|------|
| `generating` | Skill 正在主 Agent 中执行（对话区实时可见过程） |
| `completed` | 产出完成，可下载/预览 |
| `failed` | 执行出错 |

前端轮询刷新产出列表，产出过程在对话流中实时可见。

## 前后端通信

| 场景 | 方案 |
|------|------|
| 对话流式 | LangGraph Server SSE + `@langchain/react` useStream |
| 文档上传 | REST API (multipart/form-data) |
| 任务/产出查询 | REST API (前端轮询 5s) |
| Workspace CRUD | REST API |

## 前端页面

```
/                       → Workspace 首页
/workspace/[id]         → 三栏布局 (Doc | Chat | Task)
```

消息类型 UI：
- `text` → Markdown 渲染
- `tool_call(clarify_form)` → 表单组件
- `tool_call(rag_search)` → 折叠引用来源
- `reasoning` → 可折叠思考过程

## 技术栈

- **前端**: Next.js, TypeScript, Tailwind CSS, @langchain/react, @assistant-ui/react
- **后端**: Python, uv, LangChain, LangGraph
- **LLM Provider**: Dashscope OpenAI Compatible (`https://dashscope.aliyuncs.com/compatible-mode/v1`)
- **LLM Model**: `qwen-plus` (通过 `langchain-openai` 的 `ChatOpenAI` 接入)
- **Embedding Model**: `text-embedding-v2` (Dashscope, 用于 ChromaDB 向量化)
- **存储**: SQLite + ChromaDB + 文件系统
- **通信**: SSE + REST

## MVP 边界

| 包含 | 不包含 |
|------|--------|
| Workspace CRUD | 用户登录 |
| 文档上传 (PDF/Docx/MD/URL) | 文档在线编辑 |
| 解析+分片+向量化 | Excel 等复杂格式 |
| RAG 多轮对话 | 多用户协作 |
| 表单澄清 | 语音输入 |
| /ppt Skill (同步流式) | 其他 Skill |
| 产出管理面板 | WebSocket 推送 |

## 项目目录结构

```
train-agent/
├── frontend/                    # Next.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                # Workspace 首页
│   │   │   └── workspace/[id]/page.tsx # 三栏工作区
│   │   ├── components/
│   │   │   ├── chat/           # 对话 (基于 assistant-ui)
│   │   │   ├── docs/           # 文档管理
│   │   │   ├── tasks/          # 产出面板
│   │   │   └── workspace/      # 工作区
│   │   └── lib/
│   │       ├── api.ts          # REST 客户端
│   │       ├── message-utils.ts
│   │       └── user.ts         # userId (localStorage)
│   ├── package.json
│   └── next.config.ts
│
├── backend/                     # Python LangGraph
│   ├── pyproject.toml
│   ├── langgraph.json
│   ├── skills/                   # Skill 文件（纯 SKILL.md，无代码）
│   │   └── ppt/
│   │       └── SKILL.md
│   ├── src/
│   │   ├── agent/
│   │   │   ├── graph.py         # StateGraph (ReAct)
│   │   │   ├── context_manager.py
│   │   │   ├── skill_manager.py # 扫描 skills/ 目录，解析 frontmatter
│   │   │   └── prompt_manager.py
│   │   ├── tools/
│   │   │   ├── clarify_form.py
│   │   │   ├── rag_search.py
│   │   │   ├── load_skill.py   # 通用 tool：加载 SKILL.md（LangChain Skills pattern）
│   │   │   └── web_search.py
│   │   ├── services/
│   │   │   ├── workspace_service.py
│   │   │   ├── doc_service.py
│   │   │   └── task_service.py
│   │   ├── storage/
│   │   │   ├── database.py
│   │   │   ├── vector_store.py
│   │   │   └── file_store.py
│   │   └── api/
│   │       └── routes.py
│   └── tests/
│
└── docs/
    └── plans/
```
EOF; __aone_exit=$?; pwd -P > '/var/folders/hc/15n2_8n91r99sdjxcgdb82k80000gp/T/aone-copilot-cwd-1779854709546-bs3jbntrx5n.txt' 2>/dev/null; exit $__aone_exit