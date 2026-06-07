# SKILL 模块设计

## 核心理念

**结构化知识封装** — Skill 是 YAML frontmatter + Markdown 正文的文档格式，配以 `references/`、`templates/`、`scripts/`、`assets/` 子目录，形成自包含的任务知识单元。

---

## 架构设计

### 1. 技能加载流程

```
技能发现 → 扫描注册 → 缓存命令映射 → Skill 工具执行
```

| 阶段 | 实现 |
|------|------|
| 发现 | `iter_skill_index_files()` 遍历 `skills/` 目录树 |
| 注册 | `scan_skill_commands()` 构建 `{name: skill_info}` 字典 |
| 解析 | `parse_frontmatter()` 提取 YAML frontmatter |
| 预处理 | `substitute_template_vars()` 处理模板变量 |

### 2. 目录结构

```
skill-dir/
├── SKILL.md            # 必须：frontmatter + 正文
├── references/         # 可选：文档（layouts.md, themes.md 等）
├── templates/          # 可选：输出模板
├── scripts/           # 可选：可执行脚本（save_and_output.py 等）
└── assets/           # 可选：静态资源（CSS, JS 等）
```

无需数据库，文件系统即存储。

### 3. 多目录支持

```python
get_all_skills_dirs():
├── backend/skills/              # 本地技能目录
├── config.external_dirs         # 用户配置扩展目录
└── optional-skills/           # 可选官方技能
```

### 4. Skill 工具 Schema

```python
load_skill(
    skill_name: str,              # 必需，技能名称
    file_paths: list[str] = [],    # 可选，要加载的文件路径列表（最多5个）
) -> {
    "success": true,
    "name": "ppt",
    "content": "...",             # SKILL.md 内容（已预处理）
    "linked_files": {             # 所有可用关联文件
        "references": ["themes.md", ...],
        "templates": [...],
        "scripts": ["bundle.py", ...],
        "assets": [...]
    }
}
```

### 5. frontmatter Schema

```yaml
---
name: skill-name              # 必须，≤64 字符
description: 简短描述         # 必须，≤1024 字符
version: 1.0.0
platforms: [macos, linux]     # 可选，限制 OS
prerequisites:
  env_vars: [API_KEY]
  commands: [curl, jq]
---
# 正文
```

### 6. 预处理管道

```python
def preprocess(content, skill_dir, session_id):
    content = substitute_template_vars(content, skill_dir, session_id)  # ${SKILL_DIR}
    return content
```

---

## PPT 技能示例

### 目录结构

```
backend/skills/ppt/
├── SKILL.md                    # 技能主文件
├── references/
│   ├── themes.md               # 36 种主题
│   ├── layouts.md             # 31 种布局
│   ├── animations.md           # 27 种动画
│   ├── full-decks.md          # 15 个完整模板
│   ├── presenter-mode.md       # 演讲者模式
│   └── authoring-guide.md      # 创作指南
├── scripts/
│   ├── bundle.py             # 打包脚本（内联 assets）
│   └── save_and_output.py      # 原子化保存脚本
└── assets/
    ├── base.css
    ├── fonts.css
    ├── runtime.js
    └── themes/
        ├── tokyo-night.css
        └── ...
```

### 执行流程

```
Agent 调用 load_skill("ppt")
    ↓
返回 SKILL.md 内容 + linked_files
    ↓
Agent 根据需要调用 load_skill("ppt", ["references/themes.md", "references/layouts.md"])
    ↓
批量返回多个文件内容
    ↓
Agent 生成 HTML 内容
    ↓
Agent 调用 terminal(save_and_output.py) 一次性完成打包+保存
    ↓
用户可在产出面板下载独立 HTML 文件
```

---

## 关键文件

| 文件 | 职责 |
|------|------|
| `src/agent/skill_manager.py` | 技能发现、扫描、文件加载 |
| `src/tools/load_skill.py` | Skill 工具实现 |
| `skills/*/SKILL.md` | 各技能主文件 |

---

## 设计模式

### 模式 1：目录即技能

无需数据库，文件系统即存储。技能 discovery 通过扫描目录树完成。

### 模式 2：链接文件发现

```python
for subdir in ["references", "templates", "scripts", "assets"]:
    if (skill_dir / subdir).exists():
        linked_files[subdir] = glob(skill_dir / subdir / "*")
```

无需数据库声明，运行时按目录存在性自动发现。

### 模式 3：批量加载

`file_paths` 支持一次加载最多 5 个文件，减少工具调用次数。

---

## 扩展点

| 扩展方向 | 方式 |
|----------|------|
| 新技能来源 | 在 `get_all_skills_dirs()` 添加目录 |
| 新脚本类型 | 在 `scripts_dir.glob()` 添加扩展名 |
| 新平台支持 | 在 `skill_matches_platform()` 添加映射 |
| 技能编排 | 使用 Bundle 引用多个技能 |
