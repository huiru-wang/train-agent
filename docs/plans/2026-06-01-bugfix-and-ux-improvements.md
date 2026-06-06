# BugFix & UX Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers-executing-plans to implement this plan task-by-task.

**Goal:** 修复页面刷新消息丢失 BUG，优化消息交互体验（操作栏、引用气泡、system prompt、工具调用展示）

**Architecture:** 前端持久化 LangGraph threadId（per workspace），修改 assistant-ui 消息组件结构，后端调整 prompt 引用格式

**Tech Stack:** Next.js, @assistant-ui/react, @langchain/react, LangGraph, Tailwind CSS, localStorage

---

### Task 1: 修复页面刷新消息丢失 BUG

**Root Cause:** `assistant.tsx` 中 `useStream({ threadId: null })` 每次组件挂载都传 `null`，导致 LangGraph 创建全新 thread，历史消息丢失。

**Fix:** 将 threadId 持久化到 localStorage（key = `train-agent-thread-{workspaceId}`），刷新时复用已有 thread。

**Files:**
- Modify: `frontend/src/components/chat/assistant.tsx`

**Step 1: 修改 assistant.tsx，持久化 threadId**

将 `useStream` 的 `threadId` 从硬编码 `null` 改为从 localStorage 读取/存储：

```tsx
// assistant.tsx 关键变更

const THREAD_KEY_PREFIX = "train-agent-thread-";

function getPersistedThreadId(workspaceId: string): string | undefined {
  if (typeof window === "undefined") return undefined;
  return localStorage.getItem(`${THREAD_KEY_PREFIX}${workspaceId}`) || undefined;
}

function persistThreadId(workspaceId: string, threadId: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(`${THREAD_KEY_PREFIX}${workspaceId}`, threadId);
  }
}

// 在 Assistant 组件内：
const stream = useStream({
  apiUrl: LANGGRAPH_API_URL,
  assistantId: "train_agent",
  threadId: getPersistedThreadId(workspaceId) ?? null,
});

// 当 stream.threadId 变化时持久化
useEffect(() => {
  if (stream.threadId) {
    persistThreadId(workspaceId, stream.threadId);
  }
}, [stream.threadId, workspaceId]);
```

**Step 2: 验证**

1. 启动前端 `pnpm dev`
2. 打开工作区，发送消息
3. 刷新页面，确认消息仍然存在
4. 切换到另一个工作区，确认 thread 隔离

---

### Task 2: Agent 消息操作栏（复制/喜欢/不喜欢）

**Files:**
- Modify: `frontend/src/components/chat/thread.tsx`

**Step 1: 在 AssistantMessage 组件中，消息内容下方添加操作栏**

```tsx
// thread.tsx 中新增 MessageActions 组件

import { Copy, ThumbsUp, ThumbsDown, Check } from "lucide-react";

function MessageActions() {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"like" | "dislike" | null>(null);

  const handleCopy = async () => {
    // 获取当前消息文本 — 从最近的 MessagePrimitive 上下文中获取
    const messageEl = document.querySelector(
      "[data-message-id]:last-of-type .prose"
    );
    const text = messageEl?.textContent || "";
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mt-1.5 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      <button
        onClick={handleCopy}
        className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
        title="复制消息"
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <button
        onClick={() => setFeedback(feedback === "like" ? null : "like")}
        className={`rounded-md p-1 transition-colors ${
          feedback === "like"
            ? "text-green-400"
            : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
        }`}
        title="有帮助"
      >
        <ThumbsUp size={14} />
      </button>
      <button
        onClick={() => setFeedback(feedback === "dislike" ? null : "dislike")}
        className={`rounded-md p-1 transition-colors ${
          feedback === "dislike"
            ? "text-red-400"
            : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
        }`}
        title="没有帮助"
      >
        <ThumbsDown size={14} />
      </button>
    </div>
  );
}
```

**Step 2: 将 MessageActions 集成到 AssistantMessage**

```tsx
function AssistantMessage() {
  return (
    <div className="group mb-4 flex gap-3">
      <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
        <Bot size={14} />
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="prose prose-invert prose-sm max-w-none">
          <MessagePrimitive.Content
            components={{
              Text: MarkdownTextWrapper,
              Reasoning: ReasoningBlock,
            }}
          />
        </div>
        <MessageActions />
      </div>
    </div>
  );
}
```

注意：使用 `assistant-ui` 的 `useMessage` hook 获取消息文本做复制，而非 DOM 查询。需要在实现时确认 API。

**Step 3: 验证**

1. 发送消息，收到 Agent 回复
2. hover 到 Agent 消息上，确认操作栏出现（3 个 icon）
3. 点击复制 → 确认剪贴板内容
4. 点击喜欢/不喜欢 → 确认高亮切换

---

### Task 3: 来源引用气泡（结构化标记 + hover tooltip）

**分两部分：后端改 prompt 引用格式 → 前端解析渲染。**

**Files:**
- Modify: `backend/src/agent/prompt_manager.py`（引用格式）
- Modify: `frontend/src/components/chat/thread.tsx`（引用解析渲染）

**Step 1: 修改 system prompt 引用格式**

将 prompt 中的引用规范改为结构化标记：

```python
# prompt_manager.py 引用规范部分替换为：

## 引用规范
回答用户问题时，如果引用了通过 rag_search 检索到的文档内容，必须使用以下标记格式：
- 在引用内容的句末使用标记：{{ref:文档名|段落描述}}
- 示例：单元测试应该遵循AIR原则{{ref:阿里巴巴Java开发手册|第3章 单元测试规约}}
- 多个来源可分别标注在对应句子后
- 如果未使用文档内容回答，无需标注
- 标记会被前端解析为可交互的引用气泡，请确保标记格式正确
```

**Step 2: 前端解析引用标记，渲染为带编号的 tooltip 气泡**

在 `thread.tsx` 中创建自定义 Text 渲染组件，解析 `{{ref:...}}` 标记：

```tsx
// thread.tsx 新增引用组件

function CitationBadge({
  index,
  docName,
  detail,
}: {
  index: number;
  docName: string;
  detail: string;
}) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span className="inline-flex h-4 w-4 cursor-default items-center justify-center rounded-full bg-accent/20 text-[10px] font-medium text-accent align-super ml-0.5">
        {index}
      </span>
      {showTooltip && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-max max-w-xs rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-lg z-50">
          <span className="font-medium text-accent">📄 {docName}</span>
          <br />
          <span className="text-muted-foreground">{detail}</span>
        </span>
      )}
    </span>
  );
}

function MarkdownWithCitations({ text }: { text: string }) {
  // 解析 {{ref:docName|detail}} 标记
  const REF_PATTERN = /\{\{ref:([^|]+)\|([^}]+)\}\}/g;
  let refCounter = 0;
  const refs: Array<{ index: number; docName: string; detail: string }> = [];

  const processedText = text.replace(REF_PATTERN, (_, docName, detail) => {
    refCounter++;
    refs.push({ index: refCounter, docName: docName.trim(), detail: detail.trim() });
    return `[[CITE_${refCounter}]]`;
  });

  // 先用 MarkdownTextPrimitive 渲染 markdown，再后处理替换 cite placeholder
  // 实际实现：拆分文本为 segments，交替渲染 markdown 和 CitationBadge
}
```

实际实现将在 MarkdownTextWrapper 中进行 — 拦截 text prop，解析 `{{ref:...}}`，拆分为文本段和引用 badge 交替渲染。

**Step 3: 验证**

1. 上传文档，提问
2. Agent 回复中包含 `{{ref:...}}` 标记
3. 前端解析为数字角标（如 ①②），hover 显示来源 tooltip
4. 确认普通无引用回复不受影响

---

### Task 4: 优化 System Prompt — 更专业严谨

**Files:**
- Modify: `backend/src/agent/prompt_manager.py`

**Step 1: 重写 system prompt**

```python
SYSTEM_PROMPT = """你是一名资深企业培训专家，专注于基于知识库文档为用户提供专业、结构化的培训咨询服务。

## 核心职责
- 基于用户上传的培训文档进行深度问答
- 帮助用户系统性地理解和梳理培训内容
- 使用专业技能完成培训产出（如 PPT 生成）

## 回答规范
1. **结构化输出**：使用标题、分点、表格等 Markdown 格式组织回答，层次清晰
2. **内容聚焦**：只回答用户当前问题，不添加"建议您""下一步""如果您还想了解"等引导性尾巴
3. **专业严谨**：回答基于文档事实，明确区分文档内容与个人推断，不捏造信息
4. **适度引用**：对文档内容的引用要准确到具体章节或段落
5. **精炼表达**：避免冗余重复，用最少的文字传达最多的信息

## 场景限定
- 只处理与培训、学习、教育、知识管理相关的请求
- 非培训场景的请求，简要说明不在服务范围内即可，不做过多解释

## 引用规范
引用 rag_search 检索到的文档内容时，在对应句末使用结构化标记：
- 格式：{{ref:文档名|章节或段落描述}}
- 示例：单元测试应遵循 AIR 原则{{ref:阿里巴巴Java开发手册|第3章 单元测试规约}}
- 未使用文档内容时不标注

## 技能使用
通过 load_skill 工具查看和加载可用技能。
用户使用 / 命令时（如 /ppt），匹配对应技能并加载执行。
当判断某个技能适用于当前任务时，也应主动加载使用。
"""
```

**Step 2: 验证**

1. 重启后端
2. 提问，确认回答风格：结构化、无尾巴建议、引用使用新标记格式
3. 尝试非培训问题，确认简短拒绝

---

### Task 5: 工具调用消息顺序展示（不覆盖）

**Analysis:** `assistant-ui` 的 `makeAssistantToolUI` 通过 toolName 注册 UI。当 `MessagePrimitive.Content` 渲染时，它会按消息中的 parts 顺序（text、tool-call、text、tool-call...）依次渲染。如果工具调用被覆盖，问题可能出在 `convertLangChainBaseMessage` 的消息转换逻辑，或者 `MessagePrimitive.Content` 没有注册 `ToolFallback` 组件。

**Files:**
- Modify: `frontend/src/components/chat/thread.tsx`

**Step 1: 在 AssistantMessage 的 MessagePrimitive.Content 中注册 ToolFallback**

```tsx
function AssistantMessage() {
  return (
    <div className="group mb-4 flex gap-3">
      <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
        <Bot size={14} />
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="prose prose-invert prose-sm max-w-none">
          <MessagePrimitive.Content
            components={{
              Text: MarkdownWithCitations,
              Reasoning: ReasoningBlock,
              ToolFallback: ToolCallFallback,  // 确保未被 makeAssistantToolUI 覆盖的 tool 也有 UI
            }}
          />
        </div>
        <MessageActions />
      </div>
    </div>
  );
}
```

`makeAssistantToolUI` 注册的组件（rag_search, load_skill, save_output）会自动匹配对应 toolName 的 tool-call parts。ToolFallback 处理未匹配的。关键是确保 `MessagePrimitive.Content` 的 parts 顺序与原始消息一致。

**Step 2: 确认 convertLangChainBaseMessage 保留所有消息和 tool calls 顺序**

检查 `@assistant-ui/react-langchain` 的 `convertLangChainBaseMessage` 是否正确处理多个 tool calls 在同一条 AI message 中的情况。如果是 LangGraph 将多个 tool calls 放在同一条 AIMessage 的 `tool_calls` 数组中，它们应该作为多个 `tool-call` parts 依次出现。

如果消息确实被覆盖（而非顺序展示），可能需要检查 `useExternalMessageConverter` 的行为，确保每条 LangGraph 消息都被保留为独立的 thread message。

**Step 3: 验证**

1. 触发多工具调用场景（如 `/ppt`：先 clarify_form → rag_search → save_output）
2. 确认对话流中每个工具调用都按顺序展示，不被后续工具覆盖
3. 中间的文本回复也正确穿插其中

---

## 执行顺序

| 顺序 | 任务 | 依赖 |
|------|------|------|
| 1 | Task 1: 修复刷新消息丢失 | 无 |
| 2 | Task 4: 优化 System Prompt | 无 |
| 3 | Task 3: 引用标记（后端 prompt + 前端解析） | 依赖 Task 4 |
| 4 | Task 2: 消息操作栏 | 无 |
| 5 | Task 5: 工具调用顺序展示 | 无 |

Task 1 和 Task 4 可并行。Task 2 和 Task 5 可并行。Task 3 依赖 Task 4（prompt 先改好）。
