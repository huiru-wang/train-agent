# 培训 Agent — 核心 User Stories & 全链路执行过程

---

## US-1: 首次访问 — 创建工作区

**用户故事：** 作为培训管理员，我希望能创建一个工作区来组织特定培训项目的所有资料和对话。

### 预期执行过程

```mermaid
sequenceDiagram
    actor U as 用户
    participant F as 前端
    participant API as REST API
    participant DB as SQLite

    U->>F: 浏览器打开 /
    F->>F: 检查 localStorage userId
    alt 无 userId
        F->>F: 生成 uuid 存入 localStorage
    end

    F->>API: GET /api/workspaces?user_id={userId}
    API->>DB: SELECT * FROM workspace WHERE user_id=?
    DB-->>API: []
    API-->>F: 返回空列表
    F->>U: 渲染空状态 + "创建工作区" 按钮

    U->>F: 点击 "创建工作区"
    F->>U: 弹出对话框
    U->>F: 输入名称 "2026Q3新员工培训"，点击确认

    F->>API: POST /api/workspaces {user_id, name}
    API->>DB: INSERT INTO workspace (id=uuid, user_id, name)
    DB-->>API: OK
    API-->>F: {id, user_id, name}
    F->>U: 工作区卡片出现

    U->>F: 点击工作区卡片
    F->>F: router.push(/workspace/{id})
    F->>U: 进入三栏布局页面
```

---

## US-2: 上传文档 — 构建知识库

**用户故事：** 作为培训管理员，我希望上传培训文档后系统自动解析和索引，以便后续基于文档进行问答。

### 预期执行过程

```mermaid
sequenceDiagram
    actor U as 用户
    participant F as 前端
    participant API as REST API
    participant Doc as DocService
    participant FS as FileStore
    participant PDF as PyMuPDF
    participant Split as TextSplitter
    participant Vec as ChromaDB
    participant LLM as LLM
    participant DB as SQLite

    U->>F: 点击左侧文档面板 "上传"
    F->>U: 弹出文件选择器
    U->>F: 选择 "新员工手册.pdf"

    F->>API: POST /api/workspaces/{ws_id}/documents (multipart)
    API->>Doc: upload_document(ws_id, filename, content)

    Doc->>FS: save(ws_id, filename, bytes)
    FS-->>Doc: data/files/{ws_id}/新员工手册.pdf

    Doc->>DB: INSERT INTO document (status='processing')
    DB-->>Doc: {id: doc_id}

    Doc->>PDF: _parse_pdf(path)
    PDF-->>Doc: 全文文本

    Doc->>Split: split_text(text)
    Split-->>Doc: [chunk1, chunk2, ..., chunkN]

    Doc->>Vec: add_chunks(ws_id, doc_id, chunks)
    Note over Vec: collection: ws_{ws_id}<br/>metadata: {doc_id: xxx}

    Doc->>LLM: 生成摘要（200字以内）
    LLM-->>Doc: "本文档为新员工入职培训手册..."

    Doc->>DB: UPDATE document SET status='ready', summary=...
    Doc-->>API: {id, filename, status:'ready', summary}
    API-->>F: 返回文档信息

    F->>U: 文档状态更新: ✅ 就绪

    Note over F: 【Context Manager 影响】<br/>文档摘要自动进入 Layer 1<br/>下次对话 system prompt 包含该摘要
```

---

## US-3: 基于知识库多轮对话

**用户故事：** 作为培训管理员，我希望基于上传的文档与 Agent 进行问答，Agent 能引用文档内容回答问题。

### 预期执行过程

```mermaid
sequenceDiagram
    actor U as 用户
    participant F as 前端
    participant LG as LangGraph Server
    participant Agent as Agent (ReAct)
    participant CM as ContextManager
    participant RAG as rag_search
    participant Vec as ChromaDB
    participant LLM as LLM

    U->>F: 输入 "新员工入职第一周需要完成哪些培训？"
    F->>LG: useStream.submit({messages: [{content, type:"human"}]})

    LG->>Agent: 触发 ReAct Loop

    Note over Agent: Round 1
    Agent->>CM: build(system_prompt, doc_summaries, input, history)
    CM-->>Agent: [L0:System + L1:文档摘要 + L3:历史 + L2:当前问题]

    Agent->>LLM: 请求决策
    LLM-->>Agent: tool_call: rag_search(query="新员工入职第一周培训")

    Agent->>RAG: 执行 rag_search
    RAG->>Vec: query(collection="ws_{ws_id}", query, n_results=5)
    Vec-->>RAG: 5个相关 chunks
    RAG-->>Agent: 格式化的文档片段

    F-->>U: SSE ← 显示折叠的 "🔍 搜索知识库" 卡片

    Note over Agent: Round 2
    Agent->>LLM: chunks + 用户问题 → 生成回答
    LLM-->>Agent: 最终回答（无需更多 tool call）

    Agent-->>LG: 流式输出回答
    LG-->>F: SSE 流式推送
    F-->>U: 渲染 Markdown 回答 + 引用来源折叠卡片

    Note over U,F: 用户继续追问
    U->>F: "第2天的IT系统培训具体包括哪些内容？"
    F->>LG: submit(...)

    Note over Agent: 新一轮 ReAct
    Agent->>CM: build(... L3 包含上一轮问答历史)
    Agent->>RAG: rag_search("IT系统培训 内容")
    RAG->>Vec: query(...)
    Agent->>LLM: 生成详细回答
    LG-->>F: SSE 流式回答

    Note over CM: 对话持续累积<br/>L3 达到 token 70% 时触发压缩<br/>（见 US-9）
```

---

## US-4: /ppt 命令 — 生成培训 PPT

**用户故事：** 作为培训管理员，我希望基于知识库文档快速生成培训 PPT，Agent 通过对话收集需求后自动生成。

### 预期执行过程

```mermaid
sequenceDiagram
    actor U as 用户
    participant F as 前端
    participant LG as LangGraph Server
    participant Agent as Agent (ReAct)
    participant LS as load_skill
    participant SM as SkillManager
    participant CF as clarify_form
    participant RAG as rag_search
    participant SO as save_output
    participant DB as SQLite
    participant FS as FileStore

    U->>F: 输入 "/"
    F->>U: 弹出命令菜单: [/ppt 生成培训PPT]
    U->>F: 选择 /ppt，输入 "做一个关于新员工培训的PPT"
    F->>LG: submit message

    Note over Agent: Round 1 — 加载 Skill
    Agent->>Agent: 识别 /ppt 命令，检查 load_skill docstring
    Agent->>LS: load_skill(skill_name="ppt")
    LS->>SM: load_skill("ppt")
    SM-->>LS: 读取 skills/ppt/SKILL.md 全文
    LS-->>Agent: 返回 SKILL.md 内容

    F-->>U: SSE ← 显示 "📖 加载技能: ppt"

    Note over Agent: Round 2 — 收集需求（按 SKILL.md 指引）
    Agent->>CF: clarify_form(title, fields)
    CF-->>Agent: [等待用户填写]

    F-->>U: SSE ← 渲染交互式表单
    Note over F: 表单内容:<br/>· 演示主题 [文本]<br/>· 目标受众 [选择]<br/>· 幻灯片数 [选择]<br/>· 风格偏好 [选择]

    U->>F: 填写表单，点击提交
    F->>LG: 表单结果作为 human message 发送

    Note over Agent: Round 3 — 检索文档内容
    Agent->>RAG: rag_search(query="新员工入职培训 内容大纲")
    RAG-->>Agent: 5个相关 chunks

    Note over Agent: Round 4 — 生成 PPT
    Agent->>Agent: 基于 SKILL.md 指引 + 用户需求 + RAG chunks
    Agent->>Agent: LLM 生成完整 HTML 演示文稿（流式输出）

    F-->>U: SSE ← 可见生成过程

    Agent->>SO: save_output(type="ppt", title="新员工入职培训", content=html)
    SO->>FS: save(ws_id, "新员工入职培训.html", html_bytes)
    SO->>DB: INSERT INTO task (type='ppt', status='completed', result_data=...)
    SO-->>Agent: "产出已保存"

    Agent-->>LG: "✅ PPT 已生成完成！可在右侧产出面板预览下载。"
    LG-->>F: SSE 流式推送
    F-->>U: 显示确认消息

    Note over F: 右侧任务面板轮询刷新
    F->>F: GET /api/workspaces/{ws_id}/tasks
    F-->>U: 新产出卡片: "新员工入职培训" [预览] [下载]
```

---

## US-5: 删除文档

**用户故事：** 作为培训管理员，我希望能删除不再需要的文档，同时清理其向量索引。

### 预期执行过程

```mermaid
sequenceDiagram
    actor U as 用户
    participant F as 前端
    participant API as REST API
    participant Doc as DocService
    participant FS as FileStore
    participant Vec as ChromaDB
    participant DB as SQLite

    U->>F: 点击文档删除图标
    F->>U: 二次确认: "确认删除「新员工手册.pdf」？"
    U->>F: 点击确认

    F->>API: DELETE /api/workspaces/{ws_id}/documents/{doc_id}
    API->>Doc: delete_document(ws_id, doc_id)

    Doc->>FS: delete(storage_path)
    Note over FS: 删除原文件

    Doc->>Vec: delete_by_doc_id(ws_id, doc_id)
    Note over Vec: 清除该文档所有向量 chunks

    Doc->>DB: DELETE FROM document WHERE id=doc_id

    Doc-->>API: OK
    API-->>F: {ok: true}
    F->>U: 文档从列表移除

    Note over F: 【Context Manager 影响】<br/>该文档摘要从 Layer 1 移除<br/>下次对话不再包含该文档摘要
```

---

## US-6: 删除工作区

**用户故事：** 作为培训管理员，我希望能删除整个工作区，包括其中所有文档、对话和产出。

### 预期执行过程

```mermaid
sequenceDiagram
    actor U as 用户
    participant F as 前端
    participant API as REST API
    participant FS as FileStore
    participant Vec as ChromaDB
    participant DB as SQLite

    U->>F: 点击工作区删除按钮
    F->>U: 二次确认: "确认删除？所有文档、对话和产出将被永久删除。"
    U->>F: 确认删除

    F->>API: DELETE /api/workspaces/{ws_id}

    API->>FS: delete_workspace(ws_id)
    Note over FS: rm -rf data/files/{ws_id}/

    API->>Vec: delete_collection("ws_{ws_id}")
    Note over Vec: 删除整个 collection

    API->>DB: DELETE FROM workspace WHERE id=ws_id
    Note over DB: CASCADE 删除关联的<br/>document 和 task 记录

    API-->>F: {ok: true}
    F->>U: 工作区从首页移除
```

---

## US-7: Agent 拒绝非培训场景

**用户故事：** 作为产品设计者，我希望 Agent 能识别并礼貌拒绝非培训场景的请求。

### 预期执行过程

```mermaid
sequenceDiagram
    actor U as 用户
    participant F as 前端
    participant LG as LangGraph Server
    participant Agent as Agent (ReAct)
    participant LLM as LLM

    U->>F: 输入 "帮我写一个Python爬虫"
    F->>LG: submit message

    Agent->>Agent: context_mgr.build()
    Note over Agent: L0: System Prompt 包含:<br/>"只处理培训相关请求...<br/>礼貌拒绝非培训场景"

    Agent->>LLM: 请求决策
    LLM-->>Agent: 判断: 非培训场景 → 不调用任何 tool → 直接回复

    Agent-->>LG: 拒绝回复
    LG-->>F: SSE 流式推送
    F-->>U: "抱歉，我是专注于培训场景的助手，<br/>无法帮助编写代码。我可以帮你：<br/>- 整理培训文档<br/>- 回答培训内容相关问题<br/>- 生成培训PPT"
```

---

## US-8: 查看产出/任务面板

**用户故事：** 作为培训管理员，我希望在右侧面板中查看所有产出物的状态和结果。

### 预期执行过程

```mermaid
sequenceDiagram
    actor U as 用户
    participant F as 前端
    participant API as REST API
    participant DB as SQLite

    Note over F: 进入工作区后自动启动轮询

    loop 每 5 秒
        F->>API: GET /api/workspaces/{ws_id}/tasks
        API->>DB: SELECT * FROM task WHERE workspace_id=? ORDER BY created_at DESC
        DB-->>API: [task1, task2, ...]
        API-->>F: 任务列表
    end

    F->>U: 渲染任务列表
    Note over F: 📊 新员工入职培训 · PPT · ✅ 已完成 [预览][下载]<br/>📊 安全培训考核要点 · PPT · ⏳ 生成中<br/>📊 部门介绍 · PPT · ❌ 失败

    U->>F: 点击 "预览"
    F->>U: 新标签页打开 HTML 文件

    U->>F: 点击 "下载"
    F->>U: 触发浏览器下载 HTML 文件
```

---

## US-9: 上下文压缩 — 长对话场景

**用户故事：** 作为培训管理员，我在长时间多轮对话后，Agent 依然能正常回答问题，不会因为上下文过长而出错。

### 预期执行过程

```mermaid
flowchart TD
    A[对话进行到第 N 轮] --> B{context_mgr 计算 token 总量}

    B --> C[L0 System Prompt ~800 tokens]
    B --> D[L1 文档摘要 x3 ~1500 tokens]
    B --> E[L3 对话历史 ~N*3000 tokens]
    B --> F[L2 当前轮 ~500 tokens]

    C & D & E & F --> G{总量 / max_tokens > 70%?}

    G -- 否 --> H[正常继续对话<br/>不做任何处理]

    G -- 是 --> I[触发 compress_history]
    I --> J[保留最近 4 条消息]
    I --> K[前 N-4 条消息发给 LLM 压缩]

    K --> L[LLM 返回摘要 ~800 tokens<br/>历史摘要 用户讨论了入职培训流程<br/>IT系统培训内容 安全规范要点...]

    J & L --> M[L3 替换为: 摘要 + 最近4条<br/>token 大幅释放]
    M --> N[后续对话继续正常进行]

    style G fill:#f9d71c,color:#000
    style I fill:#ff6b6b,color:#fff
    style M fill:#51cf66,color:#fff
```

---

## 全链路关键路径总结

```mermaid
graph LR
    subgraph 用户入口
        WS[创建工作区]
        UPLOAD[上传文档]
    end

    subgraph 核心交互
        CHAT[知识库对话]
        PPT[/ppt 生成]
        REJECT[拒绝非培训]
    end

    subgraph 产出管理
        TASK[任务面板]
        PREVIEW[预览/下载]
    end

    subgraph 内部机制
        CTX[上下文压缩]
    end

    WS --> UPLOAD
    UPLOAD --> CHAT
    CHAT --> PPT
    CHAT --> REJECT
    PPT --> TASK
    TASK --> PREVIEW
    CHAT -.-> CTX

    style WS fill:#4dabf7,color:#fff
    style UPLOAD fill:#4dabf7,color:#fff
    style CHAT fill:#ae3ec9,color:#fff
    style PPT fill:#ae3ec9,color:#fff
    style TASK fill:#20c997,color:#fff
    style CTX fill:#868e96,color:#fff
```

| 路径 | 涉及模块 | 关键接口 |
|------|----------|----------|
| 创建工作区 | Frontend → REST → SQLite | `POST /api/workspaces` |
| 上传文档 | Frontend → REST → DocService → FileStore + PyMuPDF + ChromaDB + LLM | `POST /api/workspaces/{id}/documents` |
| 知识库对话 | Frontend → SSE → Agent(ReAct) → rag_search → ChromaDB | LangGraph SSE stream |
| /ppt 生成 | Frontend → SSE → Agent → load_skill → clarify_form → rag_search → save_output | LangGraph SSE stream |
| 产出查询 | Frontend(polling) → REST → SQLite | `GET /api/workspaces/{id}/tasks` |
| 文档删除 | Frontend → REST → DocService → FileStore + ChromaDB + SQLite | `DELETE .../documents/{id}` |
| 上下文压缩 | Agent 内部 → ContextManager → LLM | 自动触发，用户无感知 |