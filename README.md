# Train Agent

Train Agent is a training-domain agent product. The current MVP focuses on workspace-based knowledge QA, training PPT generation, and narration (script + TTS audio) generation.

## What It Runs

The local development stack has three services:

| Service | Port | Purpose |
| --- | ---: | --- |
| FastAPI backend | 8000 | REST APIs for workspaces, documents, tasks, messages, and file downloads |
| LangGraph server | 2024 | Streaming agent runtime used by the chat panel |
| Next.js frontend | 3000 | Workspace UI with document, chat, task, config, and player panels |

## Core Flow

1. Create a workspace from the homepage.
2. Upload training documents in the workspace document panel.
3. The backend stores the source file, parses it, chunks it, writes vectors to ChromaDB, and saves a summary to SQLite.
4. The chat panel sends messages to LangGraph with the current `workspace_id`.
5. The agent injects document summaries into its prompt and calls tools such as `rag_search`, `load_skill`, `save_ppt`, and `save_narration`.
6. PPT generation is driven by `backend/skills/ppt/SKILL.md` and saves output files into the task panel.
7. Narration generation is driven by `backend/skills/narration/SKILL.md`, producing per-slide scripts and optional TTS audio files.
8. Message history is persisted to SQLite and supports turn-based pagination for long conversations.
9. Workspace config (PPT style, TTS voice) is stored in `ext_data` and passed to the agent before each run.

## Repository Map

| Path | Purpose |
| --- | --- |
| `backend/src/api/routes.py` | FastAPI REST routes |
| `backend/src/api/deps.py` | Dependency injection for FastAPI process |
| `backend/src/app_context.py` | Shared AppContext bundling storage instances |
| `backend/src/agent/graph.py` | LangGraph/LangChain agent entrypoint |
| `backend/src/agent/message_history.py` | Message history callback + middleware |
| `backend/src/middlewares/` | Agent middlewares (doc context, summarization, sanitizer, logging) |
| `backend/src/tools/` | Agent tools (rag_search, load_skill, save_ppt, save_narration, etc.) |
| `backend/src/services/doc_service.py` | Document upload, parsing, chunking, summary, vector indexing |
| `backend/src/services/tts_service.py` | TTS audio generation via Dashscope |
| `backend/src/storage/` | SQLite, ChromaDB, and file storage wrappers |
| `backend/skills/ppt/` | PPT generation skill (SKILL.md + references + assets) |
| `backend/skills/narration/` | Narration script + TTS generation skill |
| `backend/tests/` | Backend unit tests |
| `frontend/src/app/` | Next.js app routes |
| `frontend/src/components/chat/` | Chat system (assistant, thread, clarify-form) |
| `frontend/src/components/config/` | Config panel (PPT style picker, voice picker) |
| `frontend/src/components/player/` | PPT preview and playback dialogs |
| `frontend/src/components/document/` | Document upload and list panel |
| `frontend/src/components/task/` | Task/output panel with parent-child hierarchy |
| `frontend/src/lib/api.ts` | Frontend REST client |
| `scripts/` | Local dev lifecycle scripts |

## Environment

Copy the example and fill in secrets:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

Important variables:

| Variable | Used By | Default |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | backend | required for Agent LLM calls |
| `DEEPSEEK_API_BASE` | backend | `https://api.deepseek.com` |
| `MAIN_MODEL` | backend | `deepseek-v4-flash` (Agent graph model) |
| `SUMMARIZATION_API_KEY` | backend | for document summarization |
| `SUMMARIZATION_MODEL` | backend | `deepseek-v4-flash` |
| `EMBEDDING_API_KEY` | backend | for vector embedding |
| `EMBEDDING_API_BASE` | backend | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `EMBEDDING_MODEL` | backend | `text-embedding-v2` |
| `TTS_API_KEY` | backend | for TTS audio generation |
| `TTS_MODEL` | backend | `qwen3-tts-flash` |
| `DATA_DIR` | backend | `./data` relative to `backend/` |
| `NEXT_PUBLIC_API_BASE` | frontend | `http://localhost:8000` |
| `NEXT_PUBLIC_LANGGRAPH_API_URL` | frontend | `http://localhost:2024` |

## Common Commands

Install frontend dependencies once:

```bash
cd frontend
pnpm install
```

If `pnpm` is not installed, use `npm install`.

Run a local health check:

```bash
./scripts/doctor.sh
```

Start all services:

```bash
./scripts/start.sh
```

Stop all services:

```bash
./scripts/stop.sh
```

Restart all services:

```bash
./scripts/restart.sh
```

Backend-only tests:

```bash
cd backend
uv run pytest tests/
```

Frontend checks:

```bash
cd frontend
pnpm lint
pnpm build
```

If `pnpm` is not installed, the scripts fall back to `npm`.

## Development Notes

- Keep runtime data under `backend/data/` or another `DATA_DIR`; do not commit generated data, logs, or local env files.
- Add new agent tools under `backend/src/tools/` and register them in `backend/src/tools/__init__.py` via `create_tools()`.
- Add new middlewares under `backend/src/middlewares/` and register them in `middlewares/__init__.py` via `create_middlewares()`.
- Add new skills as `backend/skills/<skill-name>/SKILL.md`.
- Add backend tests for storage, services, tools, and skill behavior when changing those areas.
- After frontend UI changes, run lint/build and visually verify the affected local page.
# Train Agent

Train Agent is a training-domain agent product. The current MVP focuses on workspace-based knowledge QA and training PPT generation.

## What It Runs

The local development stack has three services:

| Service | Port | Purpose |
| --- | ---: | --- |
| FastAPI backend | 8000 | REST APIs for workspaces, documents, tasks, and file downloads |
| LangGraph server | 2024 | Streaming agent runtime used by the chat panel |
| Next.js frontend | 3000 | Workspace UI with document, chat, and task panels |

## Core Flow

1. Create a workspace from the homepage.
2. Upload training documents in the workspace document panel.
3. The backend stores the source file, parses it, chunks it, writes vectors to ChromaDB, and saves a summary to SQLite.
4. The chat panel sends messages to LangGraph with the current `workspace_id`.
5. The agent injects document summaries into its prompt and calls tools such as `rag_search`, `load_skill`, and `save_output`.
6. PPT generation is driven by `backend/skills/ppt/SKILL.md` and saves output files into the task panel.

## Repository Map

| Path | Purpose |
| --- | --- |
| `backend/src/api/routes.py` | FastAPI REST routes |
| `backend/src/agent/graph.py` | LangGraph/LangChain agent entrypoint |
| `backend/src/tools/` | Agent tools |
| `backend/src/services/doc_service.py` | Document upload, parsing, chunking, summary, vector indexing |
| `backend/src/storage/` | SQLite, ChromaDB, and file storage wrappers |
| `backend/skills/` | Progressive-disclosure agent skills |
| `backend/tests/` | Backend unit tests |
| `frontend/src/app/` | Next.js app routes |
| `frontend/src/components/` | Workspace, document, chat, task, and layout UI |
| `frontend/src/lib/api.ts` | Frontend REST client |
| `scripts/` | Local dev lifecycle scripts |
| `docs/plans/` | Product and implementation planning notes |

## Environment

Copy the example and fill in secrets:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

Important variables:

| Variable | Used By | Default |
| --- | --- | --- |
| `DASHSCOPE_API_KEY` | backend | required for real LLM and embedding calls |
| `OPENAI_API_BASE` | backend | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `LLM_MODEL` | backend | `qwen-plus` for API services, `qwen3-plus` in agent graph unless overridden |
| `EMBEDDING_MODEL` | backend | `text-embedding-v2` |
| `DATA_DIR` | backend | `./data` relative to `backend/` when scripts run |
| `NEXT_PUBLIC_API_BASE` | frontend | `http://localhost:8000` |
| `NEXT_PUBLIC_LANGGRAPH_API_URL` | frontend | `http://localhost:2024` |

## Common Commands

Install frontend dependencies once:

```bash
cd frontend
pnpm install
```

If `pnpm` is not installed, use `npm install`.

Run a local health check:

```bash
./scripts/doctor.sh
```

Start all services:

```bash
./scripts/start.sh
```

Run all services in a foreground terminal:

```bash
./scripts/dev.sh
```

Stop all services:

```bash
./scripts/stop.sh
```

Restart all services:

```bash
./scripts/restart.sh
```

Run the standard verification suite:

```bash
./scripts/test.sh
```

Backend-only tests:

```bash
cd backend
uv run --extra dev pytest
```

Frontend checks:

```bash
cd frontend
pnpm lint
pnpm build
```

If `pnpm` is not installed, the scripts fall back to `npm`.

## Development Notes

- Keep runtime data under `backend/data/` or another `DATA_DIR`; do not commit generated data, logs, or local env files.
- Add new agent tools under `backend/src/tools/` and register them in `backend/src/agent/graph.py`.
- Add new skills as `backend/skills/<skill-name>/SKILL.md`.
- Add backend tests for storage, services, tools, and skill behavior when changing those areas.
- After frontend UI changes, run lint/build and visually verify the affected local page.
