# Train Agent 前端架构设计文档

> 本文档面向 AI 及开发者，旨在帮助快速理解 Train Agent 前端的整体设计、模块职责与交互流程。

---

## 一、系统总览

Train Agent 前端是一个基于 **Next.js (App Router)** 的单页应用，提供培训知识管理和 AI 对话交互界面。

### 核心交互模型

```
┌─────────────────────────────────────────────────────────────────────┐
│                        浏览器 (localhost:3000)                       │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    工作区页面（三栏布局）                       │   │
│  │                                                              │   │
│  │  ┌──────────┐  ┌────────────────────┐  ┌──────────────────┐ │   │
│  │  │ 文档面板  │  │     聊天面板        │  │    产出面板      │ │   │
│  │  │          │  │                    │  │                  │ │   │
│  │  │ 上传文档  │  │  流式对话          │  │  PPT / 报告      │ │   │
│  │  │ 文档列表  │  │  工具调用展示      │  │  预览 / 下载     │ │   │
│  │  │ 状态追踪  │  │  表单中断交互      │  │  状态追踪        │ │   │
│  │  │          │  │  Markdown 渲染     │  │                  │ │   │
│  │  └──────────┘  └────────────────────┘  └──────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│        REST API (:8000)                LangGraph Stream (:2024)      │
│        ↕ 工作区/文档/任务 CRUD          ↕ Agent 流式对话              │
└─────────────────────────────────────────────────────────────────────┘
```

**前端同时与两个后端服务通信**：
- **FastAPI (:8000)**：通过 REST API 管理工作区、文档上传/删除、任务查询
- **LangGraph (:2024)**：通过 `@langchain/react` 的 `useStream` hook 进行流式 Agent 对话

---

## 二、技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **框架** | Next.js 16 (App Router) | React Server Components + Client Components |
| **UI 库** | React 19 | 最新版 React |
| **样式** | Tailwind CSS 4 | 原子化 CSS，暗色主题 |
| **Agent 通信** | @langchain/react (`useStream`) | LangGraph 流式对话 hook |
| **图标** | lucide-react | 一致的图标风格 |
| **Markdown** | react-markdown + remark-gfm | GFM 扩展 Markdown 渲染 |
| **代码高亮** | react-syntax-highlighter (Prism) | oneDark 主题 |
| **字体** | Geist + Geist Mono | 现代等宽/无衬线字体 |
| **包管理** | pnpm | 高效依赖管理 |
| **语言** | TypeScript | 严格类型检查 |

---

## 三、目录结构

```
frontend/
├── package.json                 # 项目配置与依赖
├── next.config.ts               # Next.js 配置
├── tailwind.config.ts           # Tailwind 配置
├── tsconfig.json                # TypeScript 配置
├── postcss.config.mjs           # PostCSS 配置
├── public/                      # 静态资源
└── src/
    ├── app/                     # Next.js App Router 路由
    │   ├── layout.tsx           #   根布局（字体、全局样式）
    │   ├── globals.css          #   全局 CSS + Tailwind 导入
    │   ├── page.tsx             #   首页（工作区列表）
    │   └── workspace/
    │       └── [id]/
    │           └── page.tsx     #   工作区详情页（三栏布局）
    ├── components/              # UI 组件
    │   ├── chat/                #   聊天相关组件
    │   │   ├── assistant.tsx    #     Agent 连接 & 流上下文 Provider
    │   │   ├── chat-panel.tsx   #     聊天面板容器
    │   │   ├── thread.tsx       #     对话线程（消息渲染 + 输入框）
    │   │   └── clarify-form.tsx #     Agent 表单中断 UI
    │   ├── document/            #   文档管理组件
    │   │   └── document-panel.tsx #   文档面板（上传 + 列表 + 状态）
    │   ├── task/                #   任务/产出组件
    │   │   └── task-panel.tsx   #     产出面板（列表 + 预览 + 下载）
    │   ├── layout/              #   布局组件
    │   │   └── three-panel.tsx  #     三栏可拖拽布局
    │   └── workspace/           #   工作区组件
    │       ├── workspace-card.tsx #   工作区卡片
    │       └── create-dialog.tsx  #   创建工作区弹窗
    └── lib/                     # 工具库
        ├── api.ts               #   REST API 封装（类型定义 + 请求方法）
        └── user.ts              #   用户 ID 管理（localStorage）
```

---

## 四、页面与路由

前端只有 **2 个页面**，采用 Next.js App Router：

| 路由 | 文件 | 功能 |
|------|------|------|
| `/` | `app/page.tsx` | **首页** — 工作区列表、新建、删除 |
| `/workspace/[id]` | `app/workspace/[id]/page.tsx` | **工作区详情** — 三栏布局（文档 + 聊天 + 产出） |

### 4.1 首页 (`app/page.tsx`)

**职责**：展示当前用户的所有工作区，支持新建和删除。

**数据流**：
```
页面加载 → getUserId() 获取/生成用户 ID
         → listWorkspaces(userId) 获取列表
         → 渲染 WorkspaceCard 网格

用户操作：
  点击"新建"  → 打开 CreateDialog → createWorkspace() → 刷新列表
  点击卡片    → router.push(`/workspace/${id}`)
  点击删除    → deleteWorkspace(id) → 刷新列表
```

**用户 ID 策略**（`lib/user.ts`）：
- 首次访问时生成 `crypto.randomUUID()` 并存入 `localStorage`
- 后续访问复用，Key 为 `train-agent-user-id`
- SSR 场景返回 `"anonymous"` 兜底

### 4.2 工作区详情页 (`app/workspace/[id]/page.tsx`)

**职责**：三栏布局的主工作页面，组合文档管理、AI 对话、产出管理。

**组件组合**：
```tsx
<ThreePanel
  left={<DocumentPanel workspaceId={id} />}
  center={<ChatPanel workspaceId={id} />}
  right={<TaskPanel workspaceId={id} collapsed={...} onToggle={...} />}
/>
```

**关键行为**：
- 页面加载时通过 `getWorkspace(id)` 验证工作区存在，不存在则跳转首页
- 右侧产出面板支持折叠/展开

---

## 五、组件架构详解

### 5.1 布局组件

#### `ThreePanel` (`components/layout/three-panel.tsx`)

三栏可拖拽布局组件，是工作区页面的骨架：

```
┌──────────────┬──┬────────────────────┬──┬────────────────┐
│   Left       │░░│     Center         │░░│    Right       │
│   (文档)     │░░│     (聊天)          │░░│    (产出)      │
│              │░░│                    │░░│                │
│  width:      │  │   flex: 1          │  │  width:        │
│  280px       │  │                    │  │  300px         │
│  (可拖拽)    │  │                    │  │  (可拖拽)       │
└──────────────┴──┴────────────────────┴──┴────────────────┘
                ↑                        ↑
           左侧拖拽手柄              右侧拖拽手柄
```

**核心参数**：
- `MIN_SIDE_WIDTH = 240px`，`MAX_SIDE_WIDTH = 400px`
- 默认左侧 280px，右侧 300px
- 中间区域弹性伸缩 (`flex: 1`)
- 右侧支持折叠（`rightCollapsed`），折叠后显示为 8px 宽的展开按钮

**拖拽实现**：
- `onMouseDown` 注册 `mousemove` + `mouseup` 事件监听
- 拖拽期间设置 `cursor: col-resize` + `user-select: none`
- 通过 `useState` 更新宽度，React 重渲染

---

### 5.2 聊天组件

聊天系统是前端最复杂的模块，由三个组件分层协作：

```
┌─ Assistant (Provider) ──────────────────────────────┐
│                                                     │
│  useStream() → 管理 LangGraph 流式连接               │
│  StreamContext → 向下传递 messages/submit/stop        │
│  ResumeContext → 向下传递 interrupt resume 回调       │
│                                                     │
│  ┌─ ChatPanel (容器) ─────────────────────────────┐ │
│  │                                                │ │
│  │  ┌─ Thread (渲染) ─────────────────────────┐  │ │
│  │  │                                          │  │ │
│  │  │  消息列表渲染                             │  │ │
│  │  │  - AI 消息: Markdown + 工具调用折叠       │  │ │
│  │  │  - 用户消息: 纯文本                      │  │ │
│  │  │  - 中断表单: ClarifyForm                 │  │ │
│  │  │  输入框 + 发送/停止按钮                   │  │ │
│  │  │                                          │  │ │
│  │  └──────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

#### 5.2.1 `Assistant` (`components/chat/assistant.tsx`)

**角色**：Agent 连接管理器 + Context Provider

**核心机制**：

1. **Thread ID 管理**：
   - 页面加载时从后端获取已保存的 `thread_id`
   - 新 `thread_id` 自动通过 `updateWorkspaceThreadId()` 持久化到后端
   - Stream 报 404 时自动清空 `thread_id` 触发新会话

2. **`useStream` Hook**：
   ```typescript
   useStream({
     apiUrl: "http://localhost:2024",
     assistantId: "train_agent",
     threadId,
   })
   ```
   管理与 LangGraph Server 的流式通信，返回 `messages`, `isLoading`, `interrupt`, `submit`, `stop` 等。

3. **Context 传递**：
   - `StreamContext`：`messages`, `isLoading`, `interrupt`, `submit`, `stop`, `error`, `pendingMessage`
   - `ResumeContext`：`resume` 回调，供 `ClarifyForm` 提交表单结果

4. **消息发送**：
   ```
   submit() → stream.submit({
     messages: [{ role: "human", content }],
     workspace_id   // 注入到 Agent 状态
   })
   ```

#### 5.2.2 `ChatPanel` (`components/chat/chat-panel.tsx`)

极简容器组件，组合 `Assistant` Provider 和 `Thread` 渲染：

```tsx
<Assistant workspaceId={workspaceId}>
  <Thread />
</Assistant>
```

#### 5.2.3 `Thread` (`components/chat/thread.tsx`)

**角色**：消息渲染引擎 + 输入界面

**消息渲染规则**：

| 消息类型 | 渲染方式 |
|---------|---------|
| `human` 消息 | 右对齐气泡，纯文本 |
| `ai` 消息（文本） | 左对齐，ReactMarkdown 渲染（GFM + 代码高亮） |
| `ai` 消息（工具调用） | 可折叠的工具调用卡片（显示工具名 + 参数摘要） |
| `tool` 消息 | 隐藏不显示（工具结果已被 AI 消化） |
| `interrupt` 状态 | 渲染 `ClarifyForm` 交互表单 |

**关键功能**：
- **自动滚动**：新消息到达时自动滚动到底部
- **代码块**：语法高亮 + 复制按钮
- **引用标记**：解析 `{{ref:文档名|章节}}` 格式并渲染为引用标签
- **思考过程**：`<think>` 标签内容渲染为可折叠的 "思考过程" 区域
- **反馈按钮**：👍/👎 按钮（UI 预留）
- **停止生成**：加载中显示停止按钮

**工具调用去重**：
- 使用 `toolCallFingerprint()` 对工具调用做指纹去重
- 处理 LLM 返回的空 `tool_call.id` 问题

#### 5.2.4 `ClarifyForm` (`components/chat/clarify-form.tsx`)

**角色**：Agent 表单中断的前端 UI

**支持的字段类型**：
- `text`：文本输入框
- `select`：单选下拉
- `multiselect`：多选复选框组

**交互流程**：
```
Agent 调用 clarify_form 工具
  → LangGraph interrupt → 前端收到 interrupt 数据
  → 渲染 ClarifyForm（title + description + fields）
  → 用户填写并提交
  → resume(values) → LangGraph 恢复 Agent 执行
  → 表单变为 "✓ 已提交" 状态
```

---

### 5.3 文档组件

#### `DocumentPanel` (`components/document/document-panel.tsx`)

**角色**：文档上传和管理面板

**功能**：
- **上传**：支持多文件选择，通过 `FormData` 上传到 FastAPI
- **列表**：展示文档名、类型标签、状态图标
- **状态轮询**：当有文档处于处理中状态时，每 1.5 秒自动轮询刷新
- **删除**：点击删除按钮移除文档

**文档状态展示**：

| 状态 | 图标 | 颜色 | 标签 |
|------|------|------|------|
| `uploaded` | Loader2 (旋转) | 蓝色 | 已上传 |
| `parsing` | Loader2 (旋转) | 黄色 | 正在解析 |
| `chunking` | Loader2 (旋转) | 黄色 | 正在分块 |
| `indexing` | Loader2 (旋转) | 黄色 | 正在入库 |
| `summarizing` | Loader2 (旋转) | 黄色 | 正在理解文档 |
| `ready` | CheckCircle | 绿色 | 就绪 |
| `error` | AlertCircle | 红色 | 失败 |

**轮询优化**：仅当文档列表中存在 `ACTIVE_STATUSES` 状态时才启动定时器。

---

### 5.4 产出组件

#### `TaskPanel` (`components/task/task-panel.tsx`)

**角色**：展示 Agent 生成的产出物（PPT、报告等）

**功能**：
- **列表**：展示产出名称、类型图标、状态
- **预览**：PPT（HTML）内联预览 / 报告 Markdown 预览
- **下载**：通过 `GET /api/files/{path}` 下载文件
- **删除**：移除产出记录
- **折叠**：整个面板可折叠为窄条
- **自动刷新**：每 5 秒轮询任务列表

**产出类型**：

| 类型 | 图标 | 文件格式 |
|------|------|---------|
| `ppt` | Presentation | `.html`（自包含 HTML） |
| `report` | FileText | `.md` |

---

### 5.5 工作区组件

#### `WorkspaceCard` (`components/workspace/workspace-card.tsx`)

工作区卡片，展示名称 + 创建时间 + 删除按钮，点击进入工作区。

#### `CreateDialog` (`components/workspace/create-dialog.tsx`)

创建工作区的模态弹窗，包含名称输入 + 提交/取消按钮 + 重名错误提示。

---

## 六、数据层

### 6.1 API 封装 (`lib/api.ts`)

统一的 HTTP 请求封装，所有与 FastAPI 的通信通过此模块。

**设计特点**：
- `request<T>()` 泛型方法，自动 JSON 解析 + 错误处理
- `ApiError` 自定义错误类，携带 `status` + `detail`
- 所有方法都有详细的 console.log 调试日志
- `API_BASE` 通过 `NEXT_PUBLIC_API_BASE` 环境变量配置

**API 方法清单**：

| 方法 | 端点 | 说明 |
|------|------|------|
| `createWorkspace()` | `POST /api/workspaces` | 创建工作区 |
| `listWorkspaces()` | `GET /api/workspaces` | 列出用户工作区 |
| `getWorkspace()` | `GET /api/workspaces/{id}` | 获取工作区详情 |
| `deleteWorkspace()` | `DELETE /api/workspaces/{id}` | 删除工作区 |
| `updateWorkspaceThreadId()` | `PATCH /api/workspaces/{id}/thread` | 绑定 thread_id |
| `listDocuments()` | `GET /api/workspaces/{id}/documents` | 列出文档 |
| `uploadDocument()` | `POST /api/workspaces/{id}/documents` | 上传文档（FormData） |
| `deleteDocument()` | `DELETE /api/workspaces/{id}/documents/{doc_id}` | 删除文档 |
| `listTasks()` | `GET /api/workspaces/{id}/tasks` | 列出任务 |
| `deleteTask()` | `DELETE /api/workspaces/{id}/tasks/{task_id}` | 删除任务 |

**类型定义**：
- `Workspace`：`id, user_id, name, thread_id, created_at`
- `Document`：`id, workspace_id, filename, file_type, summary, status, error_message, created_at, updated_at`
- `DocumentStatus`：`uploaded | processing | parsing | parsed | chunking | indexing | summarizing | ready | error`
- `Task`：`id, workspace_id, type, title, status, result_data, created_at`

### 6.2 状态管理

前端 **不使用全局状态管理库**，采用以下策略：

| 状态类型 | 管理方式 | 说明 |
|---------|---------|------|
| 工作区列表 | `useState` + `useCallback` | 页面级，fetchWorkspaces 刷新 |
| 文档列表 | `useState` + 轮询 | 面板级，有活跃状态时 1.5s 轮询 |
| 任务列表 | `useState` + 轮询 | 面板级，固定 5s 轮询 |
| 对话流 | `useStream` (LangGraph) | 由 @langchain/react 管理 |
| Thread ID | `useState` + 后端持久化 | Assistant 组件管理，跨会话持久 |
| 用户 ID | `localStorage` | `lib/user.ts` 管理，浏览器级持久 |
| 面板宽度 | `useState` | ThreePanel 组件局部状态 |

---

## 七、核心交互流程

### 7.1 首次访问

```
用户打开 localhost:3000
  → layout.tsx 渲染根布局
  → page.tsx (首页)
    → getUserId() → localStorage 无值 → 生成 UUID 并存储
    → listWorkspaces(userId) → 空列表
    → 展示 "还没有工作区，创建一个开始吧"
```

### 7.2 创建工作区并进入

```
用户点击"新建工作区" → 打开 CreateDialog
  → 输入名称 → 提交
  → createWorkspace(userId, name)
    → 成功: 刷新列表，关闭弹窗
    → 409: 显示 "工作区名称已存在"

用户点击工作区卡片
  → router.push(`/workspace/${id}`)
  → workspace/[id]/page.tsx
    → getWorkspace(id) 验证工作区存在
    → 渲染 ThreePanel 三栏布局
```

### 7.3 上传文档

```
用户在文档面板点击上传 → 选择文件
  → uploadDocument(workspaceId, file) [FormData]
  → 文档立即出现在列表（status=uploaded）
  → 轮询开始（1.5s 间隔）
  → 状态变化: uploaded → parsing → chunking → indexing → summarizing → ready
  → ready 后轮询自动停止
```

### 7.4 AI 对话

```
用户在聊天面板输入消息 → 提交
  → Assistant.submit(content)
    → useStream.submit({ messages: [{role:"human", content}], workspace_id })
    → LangGraph Server 创建/复用 thread
    → 流式返回 AI 消息

  Thread 实时渲染:
    → 文本内容: ReactMarkdown 渲染
    → 工具调用: 显示可折叠的工具卡片
    → 思考过程: <think> 标签折叠展示
    → 引用标记: {{ref:...}} 渲染为标签

  如果 Agent 调用 clarify_form:
    → interrupt 事件 → 渲染 ClarifyForm
    → 用户填写提交 → resume(values)
    → Agent 继续执行
```

### 7.5 产出生成与查看

```
Agent 调用 save_output → 后端创建 Task + 保存文件
  → 产出面板轮询（5s）检测到新 Task
  → 展示在产出列表
  → 用户点击预览 → PPT: iframe 内联展示 / 报告: Markdown 渲染
  → 用户点击下载 → GET /api/files/{path} → 浏览器下载
```

---

## 八、通信架构

前端与两个后端服务的通信职责明确分离：

```
┌─────────────────────────────────────────────────────┐
│                    前端 (Next.js)                     │
│                                                     │
│  lib/api.ts ──── REST (fetch) ────→ FastAPI (:8000) │
│    工作区 CRUD                        文档/任务管理    │
│    文档上传/删除                                      │
│    任务查询                                          │
│    Thread ID 持久化                                  │
│                                                     │
│  assistant.tsx ── Stream (useStream) → LangGraph     │
│    (via @langchain/react)              (:2024)       │
│    对话消息发送                         Agent 推理     │
│    流式消息接收                         工具调用       │
│    Interrupt 处理                       会话管理      │
│    Resume 提交                                       │
└─────────────────────────────────────────────────────┘
```

**环境变量**：
| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` | FastAPI 服务地址 |
| `NEXT_PUBLIC_LANGGRAPH_API_URL` | `http://localhost:2024` | LangGraph 服务地址 |

---

## 九、UI 设计系统

### 9.1 主题

采用 **暗色主题**，通过 CSS 变量定义：

| 变量 | 用途 |
|------|------|
| `--foreground` | 主文本色 |
| `--background` | 页面背景 |
| `--muted` / `--muted-foreground` | 次要内容 |
| `--accent` / `--accent-foreground` | 强调色（按钮、高亮） |
| `--border` | 边框 |
| `--destructive` | 危险操作（删除） |

### 9.2 设计模式

- **卡片式布局**：工作区列表使用网格卡片
- **面板式布局**：工作区内三栏分屏
- **气泡式对话**：用户消息右对齐，AI 消息左对齐
- **渐进披露**：工具调用默认折叠，思考过程可展开
- **状态可视化**：文档/任务状态通过图标+颜色+文字三重提示
- **响应式**：工作区列表 1-3 列自适应

---

## 十、关键设计决策

1. **双通道通信**：REST API 处理 CRUD，LangGraph Stream 处理 AI 对话，职责清晰
2. **Context Provider 模式**：`Assistant` 组件作为 Provider 管理 Agent 连接，子组件通过 `useStreamContext()` 消费，解耦连接管理和 UI 渲染
3. **无全局状态库**：数据流简单（列表+详情），每个面板独立管理自己的数据，通过 React 原生 `useState` + `useCallback` 足够
4. **轮询而非 WebSocket**：文档状态和任务列表通过轮询同步，实现简单且场景契合（状态变化频率低）
5. **LangGraph SDK 接管对话**：不自行实现流式通信协议，完全依赖 `@langchain/react` 的 `useStream` hook，减少维护成本
6. **Thread ID 双向持久化**：前端通过 `useStream` 获取 `threadId`，再通过 REST API 持久化到后端 workspace 记录，实现跨会话的对话连续性
7. **所有组件 "use client"**：由于强依赖浏览器 API（localStorage、DOM 事件、流式通信），所有组件均为 Client Components
8. **可拖拽三栏布局**：使用原生 DOM 事件实现拖拽，避免引入额外布局库
