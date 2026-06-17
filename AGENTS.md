# Agent Collaboration Guide

## 项目概述

Train Agent 是一个 **AI 培训助手**，帮助用户基于上传的培训文档进行知识问答、PPT 生成、口播稿生成和 TTS 音频合成。

### 核心准则

**简单、稳定、好用。**

- **简单**：优先选择最简单的实现方案，不过度设计，不引入不必要的抽象层。能用一个文件解决的不拆成三个，能用标准库的不加新依赖。
- **稳定**：每次修改都要确保不破坏现有功能。变更范围要小而精确，数据兼容要向后兼容，错误处理要有 fallback。
- **好用**：面向最终用户体验思考，交互要流畅自然，状态反馈要清晰及时，产出物要开箱即用。

### 架构文档（必读）

深入理解项目设计前，请阅读以下文档：

- `docs/backend-architecture.md` — 后端四层架构、数据流、模块职责
- `docs/frontend-architecture.md` — 前端组件架构、通信模型、交互流程

### 核心技术栈

| 层 | 技术 | 注意事项 |
|----|------|---------|
| **后端** | Python ≥ 3.12, FastAPI, LangChain ≥ 1.2, LangGraph ≥ 1.1 | 使用 `langchain.agents.create_agent` 而非已废弃的 `initialize_agent` |
| **LLM** | DeepSeek (deepseek-v4-flash) | Agent 推理 + 文档摘要，通过 OpenAI 兼容接口调用 |
| **TTS** | Dashscope qwen3-tts-flash | 口播稿音频生成，非流式调用 |
| **存储** | SQLite (aiosqlite), ChromaDB ≥ 1.0, Dashscope Embedding | 所有数据按 workspace_id 隔离 |
| **前端** | Next.js 16 (App Router), React 19, Tailwind CSS 4, @langchain/react | 所有组件均为 Client Components (`"use client"`) |
| **包管理** | 后端: uv / 前端: pnpm | — |

### 双进程架构

后端由 **两个独立进程** 组成，修改时需注意影响范围：

- **FastAPI (:8000)** — REST API，管理工作区/文档/任务/消息 CRUD。依赖从 `src/api/deps.py` 初始化
- **LangGraph (:2024)** — Agent 运行时，流式对话+工具调用。依赖从 `src/agent/graph.py._make_default_graph()` 独立初始化

两个进程共享存储（SQLite + ChromaDB + FileStore），但各自有独立的实例。

### AppContext 统一依赖入口

`src/app_context.py` 定义了 `AppContext` 数据类，捆绑所有存储实例：

```python
@dataclass
class AppContext:
    db: Database
    vector_store: VectorStore
    file_store: FileStore
    skill_manager: SkillManager
```

FastAPI 通过 `deps.py` 的 `AppContext.from_env()` 创建，LangGraph 通过 `graph.py._make_default_graph()` 独立创建。

## Before Editing

- Read `README.md` for setup and commands.
- For architecture details, read `docs/backend-architecture.md` and `docs/frontend-architecture.md`.
- Prefer existing project boundaries over new abstractions:
  - REST routes: `backend/src/api/routes.py`
  - Dependency injection: `backend/src/api/deps.py`
  - App context: `backend/src/app_context.py`
  - Agent graph: `backend/src/agent/graph.py`
  - Agent state: `backend/src/agent/state.py` (workspace_id, ppt_style, voice_id, current_ppt_task_id)
  - Message history: `backend/src/agent/message_history.py`
  - Middlewares: `backend/src/middlewares/` (inject_doc_context, summarization, model_message_sanitizer, logging)
  - Agent tools: `backend/src/tools/`
  - Skills: `backend/skills/<name>/SKILL.md`
  - Document processing: `backend/src/services/doc_service.py`
  - TTS service: `backend/src/services/tts_service.py`
  - Storage: `backend/src/storage/` (database.py / vector_store.py / file_store.py)
  - Parsers: `backend/src/parsers/` (base.py / pdf / docx / markdown)
  - Frontend API client: `frontend/src/lib/api.ts`
  - Chat system: `frontend/src/components/chat/` (assistant.tsx 管理连接, thread.tsx 渲染消息)
  - Config UI: `frontend/src/components/config/` (config-panel.tsx, style-picker-dialog.tsx, voice-picker-dialog.tsx)
  - PPT player/preview: `frontend/src/components/player/` (ppt-player-dialog.tsx, ppt-preview-dialog.tsx)
  - Workspace UI panels: `frontend/src/components/`

## 常用命令

```bash
# 后端
cd backend
uv run uvicorn src.api.routes:app --reload --port 8000     # FastAPI 服务
uv run langgraph dev --port 2024                            # LangGraph Agent 服务
uv run pytest tests/                                        # 运行测试

# 前端
cd frontend
pnpm dev                                                    # 开发服务器 (:3000)
pnpm build && pnpm start                                    # 生产构建
```

## Safe Development Rules

- Do not commit or expose `.env`, `backend/.env`, logs, `backend/data/`, `.venv/`, `node_modules/`, or `.next/`.
- Do not delete runtime data unless the user explicitly asks for cleanup.
- Avoid broad rewrites. Keep changes scoped to the requested behavior.
- Do not change model defaults, data schemas, or tool availability without calling it out.
- Do not add network-dependent tests unless they are explicitly marked or isolated.
- Do not modify `langgraph.json` unless adding new graphs or changing dependencies.

## Backend Patterns

- Add or change FastAPI endpoints in `backend/src/api/routes.py`.
- Add new dependencies to `backend/src/api/deps.py` (FastAPI process) or `backend/src/agent/graph.py` (LangGraph process).
- Keep database operations in `backend/src/storage/database.py`. Tables: `workspace`, `document`, `task`, `message`.
  - `workspace` has `ext_data` JSON column for config (ppt_style, voice_id).
  - `task` has `parent_task_id` for parent-child hierarchy (e.g., narration tasks under PPT tasks).
  - `message` stores turn-based chat history for pagination and recovery.
- Keep vector behavior in `backend/src/storage/vector_store.py`. Collections are per-workspace: `ws_{workspace_id}`.
- Keep file operations in `backend/src/storage/file_store.py`. Structure: `{DATA_DIR}/files/{workspace_id}/`.
- Keep document upload/parsing/indexing orchestration in `backend/src/services/doc_service.py`. Document status flow: `uploaded → parsing → parsed → chunking → indexing → summarizing → ready | error`.
- Keep TTS audio generation in `backend/src/services/tts_service.py`.
- Register agent tools in `backend/src/tools/__init__.py` via `create_tools(ctx)`. Current tools: `clarify_form`, `rag_search`, `load_skill`, `save_ppt`, `run_skill_script`, `get_ppt_detail`, `save_narration`.
- New tools go in `backend/src/tools/`. Use `ToolRuntime[TrainAgentState]` for workspace-aware tools.
- Register middlewares in `backend/src/middlewares/__init__.py` via `create_middlewares(ctx, callback)`.
- System prompt is in `backend/src/agent/prompt_manager.py`. Dynamic doc summaries are injected via middleware in `middlewares/inject_doc_context.py`.
- Agent state (`state.py`) carries: `workspace_id`, `ppt_style`, `voice_id`, `current_ppt_task_id`.
- Add tests in `backend/tests/` for backend changes.

## Frontend Patterns

- Keep REST calls centralized in `frontend/src/lib/api.ts`. Add types alongside methods.
- Chat connection is managed by `frontend/src/components/chat/assistant.tsx` via `@langchain/react` `useStream` hook. Do not bypass this for Agent communication.
- `assistant.tsx` supports `ExternalCommand` mechanism: workspace page can inject slash commands (e.g., `/narrate`) via the `externalCommand` prop.
- Message rendering logic is in `frontend/src/components/chat/thread.tsx`. Support for tool calls, thinking blocks, and ref markers is already implemented.
- Keep workspace page composition in `frontend/src/app/workspace/[id]/page.tsx`. This page orchestrates ConfigPanel, TaskPanel, ChatPanel, DocumentPanel, PPTPreviewDialog, and PPTPlayerDialog.
- Config UI lives in `frontend/src/components/config/` (PPT style picker + voice picker, persisted via `updateWorkspaceConfig` API).
- PPT preview/edit lives in `frontend/src/components/player/ppt-preview-dialog.tsx` (iframe srcDoc, edit mode via contentEditable).
- PPT playback lives in `frontend/src/components/player/ppt-player-dialog.tsx` (slide-by-slide audio sync, fullscreen).
- Keep document, chat, task, and layout UI in their existing component folders.
- Follow the local Tailwind and component style already in the app (dark theme, CSS variables).
- No global state library — each panel manages its own state via `useState` + polling.
- For Next.js behavior, inspect `node_modules/next/dist/docs/` when needed — APIs may differ from training data.

## Skill Patterns

- New skills live at `backend/skills/<name>/SKILL.md`.
- Each skill **must** include YAML frontmatter with `name` and `description`.
- Prefer progressive disclosure: keep the initial description short, load references via `load_skill` tool on-demand.
- Current skills: `ppt` (HTML PPT generation), `narration` (口播稿 + TTS).
- Directory structure:
  ```
  backend/skills/<name>/
  ├── SKILL.md              # 技能主提示 (YAML frontmatter + Markdown instructions)
  ├── references/           # 可选: 参考文件，通过 load_skill(file_paths=[...]) 按需加载
  ├── scripts/              # 可选: 辅助脚本，通过 run_skill_script 工具执行
  └── assets/               # 可选: 静态资源（CSS/图片等）
  ```
- `${SKILL_DIR}` placeholder in SKILL.md is replaced with the actual skill directory path at load time.
- The `SkillManager` prevents directory traversal — all file paths must resolve within the skill directory.

## 问题定位指南

详见 [`docs/debug-guides.md`](docs/debug-guides.md)。
# Agent Collaboration Guide

## 项目概述

Train Agent 是一个 **AI 培训助手**，帮助用户基于上传的培训文档进行知识问答和内容生成（如 PPT）。

### 核心准则

**简单、稳定、好用。**

- **简单**：优先选择最简单的实现方案，不过度设计，不引入不必要的抽象层。能用一个文件解决的不拆成三个，能用标准库的不加新依赖。
- **稳定**：每次修改都要确保不破坏现有功能。变更范围要小而精确，数据兼容要向后兼容，错误处理要有 fallback。
- **好用**：面向最终用户体验思考，交互要流畅自然，状态反馈要清晰及时，产出物要开箱即用。

### 架构文档（必读）

深入理解项目设计前，请阅读以下文档：

- `docs/backend-architecture.md` — 后端四层架构、数据流、模块职责
- `docs/frontend-architecture.md` — 前端组件架构、通信模型、交互流程

### 核心技术栈

| 层 | 技术 | 注意事项 |
|----|------|---------|
| **后端** | Python ≥ 3.12, FastAPI, LangChain ≥ 1.2, LangGraph ≥ 1.1 | 使用 `langchain.agents.create_agent` 而非已废弃的 `initialize_agent` |
| **存储** | SQLite (aiosqlite), ChromaDB ≥ 1.0, Dashscope Embedding | 所有数据按 workspace_id 隔离 |
| **前端** | Next.js 16 (App Router), React 19, Tailwind CSS 4, @langchain/react | 所有组件均为 Client Components (`"use client"`) |
| **包管理** | 后端: uv / 前端: pnpm | — |

### 双进程架构

后端由 **两个独立进程** 组成，修改时需注意影响范围：

- **FastAPI (:8000)** — REST API，管理工作区/文档/任务 CRUD。依赖从 `src/api/deps.py` 初始化
- **LangGraph (:2024)** — Agent 运行时，流式对话+工具调用。依赖从 `src/agent/graph.py._make_default_graph()` 独立初始化

两个进程共享存储（SQLite + ChromaDB + FileStore），但各自有独立的实例。

## Before Editing

- Read `README.md` for setup and commands.
- For architecture details, read `docs/backend-architecture.md` and `docs/frontend-architecture.md`.
- Prefer existing project boundaries over new abstractions:
  - REST routes: `backend/src/api/routes.py`
  - Dependency injection: `backend/src/api/deps.py`
  - Agent graph: `backend/src/agent/graph.py`
  - Agent tools: `backend/src/tools/`
  - Skills: `backend/skills/<name>/SKILL.md`
  - Document processing: `backend/src/services/doc_service.py`
  - Storage: `backend/src/storage/` (database.py / vector_store.py / file_store.py)
  - Parsers: `backend/src/parsers/` (base.py / pdf / docx / markdown)
  - Frontend API client: `frontend/src/lib/api.ts`
  - Chat system: `frontend/src/components/chat/` (assistant.tsx 管理连接, thread.tsx 渲染消息)
  - Workspace UI panels: `frontend/src/components/`

## 常用命令

```bash
# 后端
cd backend
uv run uvicorn src.api.routes:app --reload --port 8000     # FastAPI 服务
uv run langgraph dev --port 2024                            # LangGraph Agent 服务
uv run pytest tests/                                        # 运行测试

# 前端
cd frontend
pnpm dev                                                    # 开发服务器 (:3000)
pnpm build && pnpm start                                    # 生产构建
```

## Safe Development Rules

- Do not commit or expose `.env`, `backend/.env`, logs, `backend/data/`, `.venv/`, `node_modules/`, or `.next/`.
- Do not delete runtime data unless the user explicitly asks for cleanup.
- Avoid broad rewrites. Keep changes scoped to the requested behavior.
- Do not change model defaults, data schemas, or tool availability without calling it out.
- Do not add network-dependent tests unless they are explicitly marked or isolated.
- Do not modify `langgraph.json` unless adding new graphs or changing dependencies.

## Backend Patterns

- Add or change FastAPI endpoints in `backend/src/api/routes.py`.
- Add new dependencies to `backend/src/api/deps.py` (FastAPI process) or `backend/src/agent/graph.py` (LangGraph process).
- Keep database operations in `backend/src/storage/database.py`. Tables: `workspace`, `document`, `task`.
- Keep vector behavior in `backend/src/storage/vector_store.py`. Collections are per-workspace: `ws_{workspace_id}`.
- Keep file operations in `backend/src/storage/file_store.py`. Structure: `{DATA_DIR}/files/{workspace_id}/`.
- Keep document upload/parsing/indexing orchestration in `backend/src/services/doc_service.py`. Document status flow: `uploaded → parsing → chunking → indexing → summarizing → ready | error`.
- Register agent tools in `backend/src/agent/graph.py` (tools list in `create_graph()`).
- New tools go in `backend/src/tools/`. Use `ToolRuntime[TrainAgentState]` for workspace-aware tools.
- System prompt is in `backend/src/agent/prompt_manager.py`. Dynamic doc summaries are injected via middleware in `graph.py`.
- Add tests in `backend/tests/` for backend changes.

## Frontend Patterns

- Keep REST calls centralized in `frontend/src/lib/api.ts`. Add types alongside methods.
- Chat connection is managed by `frontend/src/components/chat/assistant.tsx` via `@langchain/react` `useStream` hook. Do not bypass this for Agent communication.
- Message rendering logic is in `frontend/src/components/chat/thread.tsx`. Support for tool calls, thinking blocks, and ref markers is already implemented.
- Keep workspace page composition in `frontend/src/app/workspace/[id]/page.tsx`.
- Keep document, chat, and task UI in their existing component folders.
- Follow the local Tailwind and component style already in the app (dark theme, CSS variables).
- No global state library — each panel manages its own state via `useState` + polling.
- For Next.js behavior, inspect `node_modules/next/dist/docs/` when needed — APIs may differ from training data.

## Skill Patterns

- New skills live at `backend/skills/<name>/SKILL.md`.
- Each skill **must** include YAML frontmatter with `name` and `description`.
- Prefer progressive disclosure: keep the initial description short, load references via `load_skill` tool on-demand.
- Directory structure:
  ```
  backend/skills/<name>/
  ├── SKILL.md              # 技能主提示 (YAML frontmatter + Markdown instructions)
  ├── references/           # 可选: 参考文件，通过 load_skill(file_paths=[...]) 按需加载
  ├── scripts/              # 可选: 辅助脚本，通过 terminal 工具执行
  └── assets/               # 可选: 静态资源（CSS/图片等）
  ```
- `${SKILL_DIR}` placeholder in SKILL.md is replaced with the actual skill directory path at load time.
- The `SkillManager` prevents directory traversal — all file paths must resolve within the skill directory.

## 问题定位指南

详见 [`docs/debug-guides.md`](docs/debug-guides.md)。