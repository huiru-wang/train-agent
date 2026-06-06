# Agent Collaboration Guide

This file is the project-level guide for AI coding agents working in this repository.

## Before Editing

- Read `README.md` for the current architecture and commands.
- For frontend changes, also read `frontend/AGENTS.md`.
- Prefer existing project boundaries over new abstractions:
  - REST routes: `backend/src/api/routes.py`
  - Agent graph: `backend/src/agent/graph.py`
  - Tools: `backend/src/tools/`
  - Skills: `backend/skills/<name>/SKILL.md`
  - Storage: `backend/src/storage/`
  - Frontend API client: `frontend/src/lib/api.ts`
  - Workspace UI panels: `frontend/src/components/`

## Safe Development Rules

- Do not commit or expose `.env`, `backend/.env`, logs, `backend/data/`, `.venv/`, `node_modules/`, or `.next/`.
- Do not delete runtime data unless the user explicitly asks for cleanup.
- Avoid broad rewrites. Keep changes scoped to the requested behavior.
- Do not change model defaults, data schemas, or tool availability without calling it out.
- Do not add network-dependent tests unless they are explicitly marked or isolated.

## Backend Patterns

- Add or change FastAPI endpoints in `backend/src/api/routes.py`.
- Keep database operations in `backend/src/storage/database.py`.
- Keep vector behavior in `backend/src/storage/vector_store.py`.
- Keep file operations in `backend/src/storage/file_store.py`.
- Keep document upload/parsing/indexing orchestration in `backend/src/services/doc_service.py`.
- Register agent tools in `backend/src/agent/graph.py`.
- Add tests in `backend/tests/` for backend changes.

## Frontend Patterns

- Keep REST calls centralized in `frontend/src/lib/api.ts`.
- Keep workspace page composition in `frontend/src/app/workspace/[id]/page.tsx`.
- Keep document, chat, and task UI in their existing component folders.
- Follow the local Tailwind and component style already in the app.
- For Next.js behavior, follow `frontend/AGENTS.md` and inspect installed docs when needed.

## Skill Patterns

- New skills should be prompt-first and live at `backend/skills/<name>/SKILL.md`.
- Each skill must include YAML frontmatter with `name` and `description`.
- Prefer progressive disclosure: keep the initial skill description short and load references only when needed.
