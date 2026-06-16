# PPT 口播稿生成功能

## 概述

为已生成的 PPT 产出物生成配套口播稿（演讲稿/讲解稿），支持 RAG 增强和 TTS 音频生成。采用解耦设计：口播稿作为独立能力，通过 Agent SKILL + 工具链实现，不侵入 PPT 生成流程。

## 整体架构

```
┌─ 前端 ──────────────────────────────────────────────────────┐
│  TaskPanel (PPT task 卡片)                                  │
│    └─ [🎙️ 生成口播稿] 按钮                                  │
│         → onNarrate(taskId, title) 回调                      │
│                                                             │
│  workspace page:                                            │
│    1. setCurrentPptTaskId(taskId)                           │
│    2. 设置 /narrate 胶囊 UI                                 │
│                                                             │
│  ChatInput:                                                 │
│    显示 [🎙️ 生成口播稿] pill + 可编辑文本                   │
│    发送 → content="/narrate {用户文本}"                     │
│           payload.source_task_id=currentPptTaskId           │
│    → 发送后清空 currentPptTaskId                             │
└─────────────────────────────────────────────────────────────┘
         ↓ LangGraph
┌─ Agent (narration SKILL 引导) ─────────────────────────────┐
│  1. 从 runtime.state.current_ppt_task_id 获取 task ID       │
│  2. 调用 get_ppt_detail(task_id) 获取结构化大纲             │
│  3. 对每张 slide 的 keywords 调用 rag_search 获取原文       │
│  4. 生成逐页口播稿文本                                      │
│  5. 调用 save_narration 保存 + 触发异步 TTS                │
│                                                             │
│  Fallback:                                                  │
│  - 大纲不存在 → 从 HTML 解析 + 提示用户                     │
│  - RAG 无结果 → 仅基于大纲生成 + 标注                       │
│  - 文档已删除 → 提示降级，继续生成                           │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─ save_narration 工具 ──────────────────────────────────────┐
│  1. 创建 narration task (parent_task_id = ppt task id)      │
│  2. 保存口播稿文本 → result_data (status: "completed_text") │
│  3. 异步 TTS 串行执行：                                     │
│     逐页调用 TTS API → 保存音频 → 更新 result_data         │
│  4. 全部完成 → status: "completed"                          │
│  5. 任何失败 → status: "tts_failed"                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Task 1: 数据库变更 — parent_task_id + list_tasks

### 1.1 task 表新增 parent_task_id 列

文件：`backend/src/storage/database.py`

- `_migrate_tables()` 新增迁移：
  ```sql
  ALTER TABLE task ADD COLUMN parent_task_id TEXT REFERENCES task(id) ON DELETE SET NULL;
  CREATE INDEX IF NOT EXISTS idx_task_parent ON task(parent_task_id);
  ```

- `create_task()` 签名新增 `parent_task_id: str = None`

### 1.2 list_tasks 只查 PPT 任务 + 嵌套子任务

```python
async def list_tasks(self, workspace_id: str) -> list[dict]:
    # 1. 只查 type='ppt' 的顶层任务
    cursor = await self.connection.execute(
        "SELECT * FROM task WHERE workspace_id = ? AND type = 'ppt' ORDER BY created_at DESC",
        (workspace_id,),
    )
    parents = [dict(row) for row in await cursor.fetchall()]

    # 2. 查询这些 PPT 任务的子任务
    if parents:
        parent_ids = [p["id"] for p in parents]
        placeholders = ",".join("?" * len(parent_ids))
        cursor = await self.connection.execute(
            f"SELECT * FROM task WHERE parent_task_id IN ({placeholders}) ORDER BY created_at",
            parent_ids,
        )
        children_map = {}
        for row in await cursor.fetchall():
            child = dict(row)
            children_map.setdefault(child["parent_task_id"], []).append(child)
        for parent in parents:
            parent["children"] = children_map.get(parent["id"], [])
    return parents
```

### 1.3 新增辅助方法

```python
async def get_task(self, task_id: str) -> dict | None:
    """获取单个 task"""

async def get_task_result_data(self, task_id: str) -> dict:
    """获取 task 的 result_data 解析为 dict"""
```

---

## Task 2: save_output → save_ppt（专用 PPT 保存工具）

### 2.1 重命名

文件：`backend/src/tools/save_output.py` → 重命名为 `backend/src/tools/save_ppt.py`

- `save_output_artifact` → `save_ppt_artifact`
- `create_save_output_tool` → `create_save_ppt_tool`
- 移除 `type` 参数（固定为 "ppt"）
- 新增 `outline: str = ""` 参数（JSON 字符串）

### 2.2 outline JSON Schema

```json
{
  "type": "object",
  "required": ["title", "total_slides", "slides"],
  "properties": {
    "title":        { "type": "string" },
    "audience":     { "type": "string" },
    "purpose":      { "type": "string" },
    "total_slides": { "type": "integer" },
    "style":        { "type": "string" },
    "slides": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["number", "title", "key_points", "keywords"],
        "properties": {
          "number":      { "type": "integer" },
          "title":       { "type": "string" },
          "key_points":  { "type": "array", "items": { "type": "string" } },
          "keywords":    { "type": "array", "items": { "type": "string" } },
          "source_refs": { "type": "array", "items": { "type": "string" } },
          "notes":       { "type": "string" }
        }
      }
    }
  }
}
```

### 2.3 result_data 结构

```json
{
  "file_path": "...",
  "filename": "...",
  "ppt_style": "bold-signal",
  "outline": { /* 上述 JSON 大纲 */ }
}
```

- `ppt_style` 从 `runtime.state.get("ppt_style", "")` 自动读取
- `outline` 从工具参数读取，解析 JSON 后写入

### 2.4 全链路同步更名

- `backend/src/tools/__init__.py`：`create_save_output_tool` → `create_save_ppt_tool`
- `backend/skills/ppt/SKILL.md` Phase 4：`save_output(...)` → `save_ppt(...)`
- `frontend/src/components/chat/thread.tsx`：toolCall key `save_output` → `save_ppt`

---

## Task 3: SKILL.md 大纲表格增加关键词列

文件：`backend/skills/ppt/SKILL.md`

Phase 2 (Step 2.1) 大纲表格新增 `关键词` 列：

```md
| # | 标题 | 核心内容 | 关键词 | 视觉建议 | 依据/来源 |
|---|------|----------|--------|----------|-----------|
| 1 | ... | ... | 消防安全,新员工,入职培训 | ... | ... |
```

Phase 4 (Step 4.1) `save_ppt` 调用增加 `outline` 参数：

```
save_ppt(
  title="<presentation title>",
  content="<full self-contained HTML>",
  filename="<safe-filename>.html",
  outline=<JSON string of structured outline>
)
```

---

## Task 4: TrainAgentState 新增 current_ppt_task_id

文件：`backend/src/agent/state.py`

```python
class TrainAgentState(AgentState):
    workspace_id: str
    ppt_style: str
    current_ppt_task_id: str  # 当前操作的 PPT task ID（口播稿生成时使用，为空时忽略）
```

**生命周期**：单次临时状态。前端 submit 时携带，发送后立即清空。Agent 通过 `runtime.state.get("current_ppt_task_id", "")` 读取。

---

## Task 5: 新增 get_ppt_detail 工具

文件：`backend/src/tools/get_ppt_detail.py`

```python
def create_get_ppt_detail_tool(db: Database):
    @tool
    async def get_ppt_detail(
        runtime: ToolRuntime[TrainAgentState],
        task_id: str,
    ) -> str:
        """获取指定 PPT 任务的详细信息，包括结构化大纲、风格、文件路径等。
        用于生成口播稿时获取幻灯片结构。
        
        Args:
            task_id: PPT 任务的 ID
        """
```

返回文本格式：

```
PPT 标题：新员工消防培训
风格：bold-signal
共 12 页
文件路径：...

第 1 页：封面：新员工消防培训
  要点：培训主题介绍, 培训目标概述
  关键词：消防安全, 新员工入职, 安全意识

第 2 页：火灾的基本知识
  ...
```

如果大纲不存在：返回提示"该 PPT 任务未保存结构化大纲信息。"

注册：`tools/__init__.py` 中 `create_tools()` 添加。

---

## Task 6: 新增 save_narration 工具

文件：`backend/src/tools/save_narration.py`

### 6.1 工具签名

```python
def create_save_narration_tool(db, file_store, tts_service):
    @tool
    async def save_narration(
        runtime: ToolRuntime[TrainAgentState],
        parent_task_id: str,     # 关联的 PPT task ID
        title: str,              # 口播稿标题
        slides: str,             # JSON: [{"number":1, "title":"...", "text":"..."}]
        language: str = "zh",    # 语言：zh | en
        voice: str = "",         # 音色，默认从 workspace.ext_data.voice_id 读取
    ) -> str:
```

### 6.2 执行流程

1. 验证 `parent_task_id` 存在且 type="ppt"
2. 创建 narration task（parent_task_id = ppt task id），status="narrating"
3. 保存口播稿文本文件 → `files/{workspace_id}/outputs/{title}_narration.md`
4. 写入 result_data：`{ "slides": [...], "language": "zh", "voice": "Cherry", "text_file_path": "...", "audio_files": {} }`
5. 更新 status → "tts_generating"
6. 触发异步 TTS 管线（`asyncio.create_task`）

### 6.3 TTS 异步管线

串行执行，逐页更新：

```python
async def _tts_pipeline(db, file_store, tts_service, task_id, workspace_id, slides, voice, title):
    audio_files = {}
    try:
        for slide in slides:
            audio_bytes = await tts_service.synthesize(text=slide["text"], voice=voice)
            filename = f"{safe_title}_slide{slide['number']}.mp3"
            file_path = await file_store.save_async(workspace_id, f"outputs/{filename}", audio_bytes)
            audio_files[str(slide["number"])] = {"file_path": file_path, "filename": filename}
            # 逐页更新 result_data
            current = await db.get_task_result_data(task_id)
            current["audio_files"] = audio_files
            current["tts_progress"] = slide["number"]
            await db.update_task(task_id, result_data=json.dumps(current, ensure_ascii=False))
        # 全部完成
        await db.update_task(task_id, status="completed")
    except Exception as exc:
        current = await db.get_task_result_data(task_id)
        current["tts_error"] = f"Slide {slide['number']} TTS failed: {exc}"
        await db.update_task(task_id, status="tts_failed",
                             result_data=json.dumps(current, ensure_ascii=False))
```

注册：`tools/__init__.py` 中 `create_tools()` 添加。

---

## Task 7: 新增 TTS Service

文件：`backend/src/services/tts_service.py`

```python
class TTSService:
    def __init__(self):
        self.api_base = os.getenv("TTS_API_BASE")
        self.api_key = os.getenv("TTS_API_KEY")
        self.model = os.getenv("TTS_MODEL")

    async def synthesize(self, text: str, voice: str = "Cherry") -> bytes:
        """调用 TTS API 生成单个音频，返回音频字节。"""
        # POST {api_base} with { model, input: { text, voice } }
        # Authorization: Bearer {api_key}
```

初始化：在 `deps.py` 中创建 `tts_service = TTSService()`，传入 `create_save_narration_tool`。不改 AppContext。

---

## Task 8: 新增 narration SKILL

文件：`backend/skills/narration/SKILL.md`（仅此一个文件）

```yaml
---
name: narration
description: 为已有的 PPT 产出物生成口播稿（演讲稿/讲解稿），支持 RAG 增强和 TTS 音频生成。当用户要求为某个 PPT 生成口播稿时使用。
---
```

SKILL 正文要点：

1. **获取大纲**：通过 `get_ppt_detail(task_id)` 获取 PPT 结构化大纲
   - task_id 从 `runtime.state.current_ppt_task_id` 读取
   - Fallback：大纲不存在 → 告知用户，从 HTML 解析幻灯片结构

2. **RAG 增强检索**：对每张 slide 的 `keywords`，调用 `rag_search` (top_k=3)
   - Fallback：RAG 无结果 → 标注"该页无参考资料"
   - Fallback：文档已删除（知识库为空）→ 告知用户，基于大纲生成

3. **口播稿写作规范**：
   - 逐页输出：`【第N页：标题】\n口播内容`
   - 口语化、自然流畅，像真人讲师讲解
   - 基于 RAG 原文展开详细讲解，不复述要点
   - 页间衔接自然（"接下来..."、"了解了XX之后..."）
   - 默认中文，用户指定英文时切换，不混用
   - 每页 100-250 字
   - 第 1 页含开场白，最后一页含总结

4. **保存**：调用 `save_narration(parent_task_id, title, slides, language, voice)`

5. **定制化**：如果用户消息附带额外要求（如"语气活泼"、"重点第三章"），融入生成

---

## Task 9: 前端 — TaskPanel 口播稿按钮 + 子任务渲染

文件：`frontend/src/components/task/task-panel.tsx`

### 9.1 PPT task 卡片新增 action

PPT 类型、status=completed 时显示 [🎙️ 生成口播稿] 按钮，点击触发 `onNarrate(taskId, title)`。

### 9.2 子任务渲染

PPT task 下方缩进显示 children（narration 类型）：

状态配置：
- `narrating`：⏳ "文本生成中"
- `tts_generating`：⏳ "音频生成中 {tts_progress}/{total}"
- `tts_failed`：⚠️ "音频生成失败"
- `completed`：✅ "已完成"（可下载文本 + 音频）

### 9.3 Props 变更

```ts
interface TaskPanelProps {
  workspaceId: string;
  onNarrate?: (taskId: string, title: string) => void;
}
```

---

## Task 10: 前端 — 胶囊 UI + /narrate 命令

### 10.1 新增 /narrate slash command

文件：`frontend/src/components/chat/thread.tsx`

```ts
SLASH_COMMANDS 新增:
{
  command: "/narrate",
  label: "生成口播稿",
  description: "为指定 PPT 生成配套口播稿",
  icon: <Mic size={14} />,
}
```

HumanBubble 的 slash 解析逻辑自动处理 `/narrate` 消息渲染。

### 10.2 ChatInput 外部注入 capsule

ChatInput 需要能从外部接收 `activeCommand`：
- 新增 prop：`externalCommand?: SlashCommand`
- 当 `externalCommand` 变化时，设置 `activeCommand`
- 输入框显示 pill + 可编辑文本

### 10.3 组件通信链路

```
TaskPanel [🎙️] 点击
  → onNarrate(taskId, title)
    → workspace page: setCurrentPptTaskId(taskId) + setNarrateTrigger(true)
      → ChatPanel: 接收 narrateTrigger
        → Thread → ChatInput: 设置 /narrate pill
          → 用户编辑/确认发送
            → submit("/narrate {用户文本}")
            → payload: { current_ppt_task_id: taskId }
            → 发送后清空 currentPptTaskId + narrateTrigger
```

### 10.4 Assistant submit 变更

文件：`frontend/src/components/chat/assistant.tsx`

```ts
interface AssistantProps {
  workspaceId: string;
  pptStyle?: string;
  currentPptTaskId?: string;           // 新增
  onPptTaskIdConsumed?: () => void;    // 新增
}
```

submit payload 新增 `current_ppt_task_id`：

```ts
streamRef.current.submit({
  messages: [{ type: "human", content }],
  workspace_id: workspaceId,
  ppt_style: pptStyle || "",
  current_ppt_task_id: currentPptTaskId || "",
}, { config: { recursion_limit: 30 } });
// 发送后调用 onPptTaskIdConsumed?.()
```

---

## Task 11: 前端 — api.ts 变更

文件：`frontend/src/lib/api.ts`

- `Task` 接口新增 `children?: Task[]`
- 无需新增 `getTask` 接口

---

## Task 12: workspace page 状态编排

文件：`frontend/src/app/workspace/[id]/page.tsx`

新增 state：

```ts
const [currentPptTaskId, setCurrentPptTaskId] = useState("");
const [narrateTrigger, setNarrateTrigger] = useState(false);
```

- `TaskPanel` 传入 `onNarrate` 回调
- `ChatPanel` 传入 `currentPptTaskId`、`narrateTrigger`、`onPptTaskIdConsumed`

---

## Task 13: thread.tsx toolCall 渲染

文件：`frontend/src/components/chat/thread.tsx`

- `save_output` key → `save_ppt`（Task 2 已完成）
- 新增 `save_narration` toolCall 渲染配置
- 新增 `get_ppt_detail` toolCall 渲染配置
- `SLASH_COMMANDS` 新增 `/narrate`

---

## 新增文件清单

| 文件 | 用途 |
|------|------|
| `backend/src/tools/save_ppt.py` | PPT 专用保存工具（替代 save_output.py） |
| `backend/src/tools/get_ppt_detail.py` | 获取 PPT 任务详情工具 |
| `backend/src/tools/save_narration.py` | 保存口播稿 + 触发 TTS 工具 |
| `backend/src/services/tts_service.py` | TTS API 调用封装 |
| `backend/skills/narration/SKILL.md` | 口播稿生成技能（仅此一个文件） |

## 修改文件清单

| 文件 | 变更 |
|------|------|
| `backend/src/storage/database.py` | parent_task_id 列迁移、create_task 签名、list_tasks 改为只查 ppt + 嵌套 children、新增 get_task / get_task_result_data |
| `backend/src/agent/state.py` | 新增 `current_ppt_task_id` 字段 |
| `backend/src/tools/__init__.py` | 注册 get_ppt_detail、save_ppt（替代 save_output）、save_narration |
| `backend/src/api/deps.py` | 初始化 TTSService，传给 create_save_narration_tool |
| `backend/skills/ppt/SKILL.md` | Phase 2 大纲增加关键词列、Phase 4 改为 save_ppt + outline 参数 |
| `backend/src/tools/save_output.py` | 删除（被 save_ppt.py 替代） |
| `frontend/src/lib/api.ts` | Task 接口新增 children |
| `frontend/src/components/task/task-panel.tsx` | 口播稿按钮、子任务渲染、新状态配置 |
| `frontend/src/app/workspace/[id]/page.tsx` | currentPptTaskId state、onNarrate 回调 |
| `frontend/src/components/chat/chat-panel.tsx` | 透传 currentPptTaskId、narrateTrigger |
| `frontend/src/components/chat/assistant.tsx` | submit payload 新增 current_ppt_task_id |
| `frontend/src/components/chat/thread.tsx` | /narrate 命令、save_narration/get_ppt_detail toolCall 渲染、ChatInput 外部注入 capsule |
