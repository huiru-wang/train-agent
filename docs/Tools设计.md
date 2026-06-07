# Tools 设计

## 概览

Tools 是 Agent 与外部世界交互的接口。当前系统定义了 5 个核心工具：

| 工具 | 功能 | 输入 |
|------|------|------|
| `terminal` | 执行 shell 命令 | `command`, `workdir?`, `timeout?`, `background?` |
| `rag_search` | 知识库向量检索 | `query`, `top_k?` |
| `load_skill` | 加载技能/文件 | `skill_name`, `file_paths?` |
| `save_output` | 保存产出物 | `type`, `title`, `content`, `filename?` |
| `clarify_form` | 信息收集表单 | Agent 内部生成 |

---

## Terminal 工具（详解）

### Schema

```python
terminal(
    command: str,                    # 必需，要执行的命令
    workdir: str = None,            # 可选，工作目录（必须是绝对路径）
    timeout: int = 60,              # 可选，超时秒数（默认60s）
    background: bool = False         # 可选，是否后台执行
) -> str
```

### 安全设计

#### 1. 路径安全校验

```python
_WORKDIR_META_CHARS = re.compile(r"[;&|`$(){}[\]!?*<>~\"\\]")

def _validate_workdir(workdir: Optional[str]) -> Optional[str]:
    if not workdir:
        return None
    if not os.path.isabs(workdir):
        raise ValueError(f"workdir must be absolute, got: {workdir}")
    if _WORKDIR_META_CHARS.search(workdir):
        raise ValueError(f"workdir contains unsafe chars: {workdir}")
    if not os.path.isdir(workdir):
        raise ValueError(f"workdir does not exist: {workdir}")
    return workdir
```

#### 2. 命令构造

```python
if validated_workdir:
    safe_workdir = shlex.quote(validated_workdir)
    shell_command = f"cd {safe_workdir} && {command}"
else:
    shell_command = command
```

使用 `shlex.quote()` 安全嵌入路径，防止 shell 注入。

#### 3. 退出码语义化

某些命令返回非 0 退出码并不代表错误：

| 命令 | 退出码 | 含义 |
|------|---------|------|
| `grep` | 1 | 无匹配（非错误） |
| `find` | 1 | 未找到文件（非错误） |

```python
def _interpret_exit_code(returncode: int, command: str) -> str:
    if returncode == 0:
        return "success"
    if returncode == 1 and "grep" in command:
        return "no matches found (semantic success)"
    if returncode == 1 and command.strip().startswith("find"):
        return "no matches found (semantic success)"
    return f"exit code {returncode}"
```

### 返回格式

#### 成功

```
<stdout>
```

#### 失败

```
Exit code: 1 (no matches found (semantic success))
stdout:
<内容>
stderr:
<错误>
```

#### 超时

```
错误: 命令执行超时（60秒）
命令: sleep 100
```

### 使用示例

```python
# 基本命令
terminal(command="ls -la")

# 指定工作目录
terminal(
    command="python3 script.py",
    workdir="/path/to/project"
)

# 带超时
terminal(
    command="python3 train.py --epochs 1000",
    timeout=300  # 5分钟
)

# 后台执行
terminal(
    command="python3 server.py",
    background=True
)
```

### PPT 保存流程（原子化）

```python
# Agent 调用 save_and_output.py 一次性完成
terminal(
    command="""python3 ${SKILL_DIR}/scripts/save_and_output.py '{
        "workspace_id": "${WORKSPACE_ID}",
        "content": "<HTML>",
        "filename": "output.html"
    }'""",
    workdir="/absolute/path/to/backend"
)
```

脚本自动完成：
1. 打包（内联 `./assets/` 引用）
2. 保存到 files 目录
3. 返回 JSON 结果

---

## RAG Search 工具

### Schema

```python
rag_search(
    query: str,           # 检索查询
    top_k: int = 5       # 返回数量
) -> str                 # Markdown 格式的检索结果片段
```

### 返回格式

```
[片段1] 📄 文档名.pdf | 标题 | p.页码
内容摘要...

[片段2] 📄 ...
```

---

## Load Skill 工具

### Schema

```python
load_skill(
    skill_name: str,              # 技能名称
    file_paths: list[str] = []    # 要加载的文件（可选）
) -> str                         # JSON 格式
```

### 返回格式

```json
{
  "success": true,
  "name": "ppt",
  "content": "SKILL.md 正文...",
  "linked_files": {
    "references": ["themes.md", ...],
    "scripts": ["save_and_output.py", ...],
    "assets": [...]
  }
}
```

### 批量加载

```python
load_skill(
    skill_name="ppt",
    file_paths=["references/themes.md", "references/layouts.md"]
)
```

返回：

```json
{
  "success": true,
  "name": "ppt",
  "files": {
    "references/themes.md": "...",
    "references/layouts.md": "..."
  },
  "linked_files": {...}
}
```

---

## Save Output 工具

### Schema

```python
save_output(
    type: str,        # 产出类型（ppt, report）
    title: str,       # 标题
    content: str,     # 内容
    filename: str = ""  # 可选文件名
) -> str
```

### 职责

- **纯抽象流程**：不包含业务逻辑
- **创建数据库任务记录**
- **保存文件到 storage**

注：打包逻辑由 skill 内部闭环处理（`save_and_output.py`）。

---

## Clarify Form 工具

### 行为

Agent 通过 `clarify_form` 工具暂停执行，等待用户填写表单：

```json
{
  "type": "tool_call",
  "name": "clarify_form",
  "args": {
    "title": "PPT 配置确认",
    "description": "请确认以下选项",
    "fields": [
      {"name": "audience", "label": "目标受众", "type": "select", "options": [...], "required": true},
      {"name": "style", "label": "视觉风格", "type": "select", "options": [...], "required": true}
    ]
  }
}
```

### UI 渲染

前端根据 `clarify_form` 工具调用渲染表单 UI，用户提交后以 `tool` 消息形式返回：

```
用户填写的表单结果: {"audience": "技术团队", "style": "tokyo-night"}
```

---

## 工具注册

工具在 Graph 创建时注册：

```python
# src/agent/graph.py
tools = [
    clarify_form,
    rag_tool,
    load_skill_tool,
    terminal,
    save_output_tool,
]
```

---

## 安全架构

| 机制 | 实现 |
|------|------|
| 危险命令审批 | `_check_all_guards()` → `tools.approval` 集中审批流 |
| workdir 白名单校验 | `_WORKDIR_SAFE_RE` 允许列表，拒绝 shell 元字符 |
| Sudo 密码处理 | 支持 `SUDO_PASSWORD` 环境变量 |
| 输出清理 | ANSI 转义序列 stripping + 敏感信息 redact |
| 超时保护 | `asyncio.wait_for` + `process.kill()` |

---

## 关键文件

| 文件 | 职责 |
|------|------|
| `src/tools/terminal_tool.py` | Terminal 工具实现 |
| `src/tools/rag_search.py` | RAG 检索工具 |
| `src/tools/load_skill.py` | Skill 加载工具 |
| `src/tools/save_output.py` | 产出保存工具 |
| `src/agent/graph.py` | 工具注册 |
