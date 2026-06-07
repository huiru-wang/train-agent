---
name: ppt
description: 当用户需要生成培训PPT、课件演示文稿时使用。基于 html-ppt 模板系统生成专业级 HTML 演示文稿，支持 36 种主题、31 种布局、27 种动画。
---

# 培训PPT生成技能（html-ppt 集成版）

基于 html-ppt 模板系统，结合知识库 RAG 检索，生成专业级零依赖 HTML 演示文稿。

## 核心原则

1. **模板驱动** — 始终从 html-ppt 的布局模板组合，不从零写 HTML
2. **零依赖** — 单个 HTML 文件，打包后无外部依赖
3. **视口适配** — 每张幻灯片精确适配 100vh，禁止滚动
4. **培训导向** — 结构清晰，要点突出，适合教学场景

## 资产引用规则

生成的 HTML 中，所有资产通过相对路径引用（`./assets/`）：

```html
<link rel="stylesheet" href="./assets/base.css">
<link rel="stylesheet" href="./assets/fonts.css">
<link rel="stylesheet" id="theme-link" href="./assets/themes/{theme-name}.css">
<link rel="stylesheet" href="./assets/animations/animations.css">
<script src="./assets/runtime.js"></script>
```

如需 Canvas FX 动画，额外引用：
```html
<script src="./assets/animations/fx-runtime.js"></script>
```

> **注意**：这些相对路径会在打包步骤中被内联为 HTML 内嵌内容，最终产物无任何外部依赖。

## 执行流程

### 第一步：了解需求

根据用户输入和对话上下文，判断还需要收集哪些信息。**不要照搬固定模板**，动态构建 `clarify_form`。

#### 必须确认的信息

#### 必须确认的信息

- **培训主题** — 如用户已明确（如 `/ppt Java开发规范`），直接采用，无需再问
- **视觉风格** — 从 36 个主题中推荐 3-5 个最合适的作为选项
- **内容风格** — 决定用语和表达方式：严谨正式 / 轻松易懂 / 技术干货

#### 按需收集（根据上下文智能判断是否需要）

- **目标受众** — 如果从对话历史能推断（如之前讨论过"新员工培训"），则跳过
- **培训时长** — 15分钟/30分钟/1小时，影响内容深度和页数（可根据时长自动推算页数，无需再单独问页数）
- **内容侧重** — 理论讲解 / 案例驱动 / 实操清单 / 速查手册，决定幻灯片的组织方式
- **互动元素** — 是否插入思考题、讨论环节、自查清单等提升培训参与感的内容
- **演讲者备注** — 是否生成逐字稿（html-ppt 支持按 S 键查看演讲者备注）
- **重点内容** — 如果知识库文档已充分覆盖主题，则跳过
- **补充要求** — 自由文本，用于兜底个性化需求（如"多用代码示例"、"加入团队实际案例"等）
#### 主题推荐逻辑

根据培训场景和受众推荐主题选项：

| 场景 | 推荐主题 |
|------|---------|
| 技术培训 / 编程规范 | `tokyo-night`, `catppuccin-mocha`, `blueprint`, `dracula` |
| 管理层汇报 / 正式场合 | `corporate-clean`, `swiss-grid`, `minimal-white` |
| 新人入职 / 通识培训 | `soft-pastel`, `aurora`, `catppuccin-latte` |
| 安全 / 合规培训 | `nord`, `arctic-cool`, `solarized-light` |
| 产品发布 / 宣讲 | `glassmorphism`, `pitch-deck-vc`, `magazine-bold` |
| 用户说"酷一点"/"科技感" | `cyberpunk-neon`, `vaporwave`, `neo-brutalism` |
| 学术 / 研究分享 | `academic-paper`, `editorial-serif`, `gruvbox-dark` |

如需完整主题列表，使用 `load_skill` 加载 `references/themes.md`。

#### 示例：动态构建表单

用户说 `/ppt Java开发规范培训`，知识库有 Java 开发手册：

```json
{
  "title": "PPT 配置确认",
  "description": "主题已确认：Java开发规范培训。请确认以下选项：",
  "fields": [
    {
      "name": "audience",
      "label": "目标受众",
      "type": "select",
      "options": ["新员工", "技术团队", "全员"],
      "required": true
    },
    {
      "name": "style",
      "label": "视觉风格",
      "type": "select",
      "options": ["tokyo-night（深色科技）", "catppuccin-mocha（柔和深色）", "blueprint（蓝图风）", "minimal-white（简洁白）"],
      "required": true
    },
    {
      "name": "duration",
      "label": "培训时长",
      "type": "select",
      "options": ["15分钟（5-8页）", "30分钟（10-15页）", "1小时（15-20页）"],
      "required": true
    },
    {
      "name": "tone",
      "label": "内容风格",
      "type": "select",
      "options": ["严谨正式", "轻松易懂", "技术干货"],
      "required": true
    },
    {
      "name": "focus",
      "label": "内容侧重",
      "type": "select",
      "options": ["理论讲解", "案例驱动", "实操清单", "速查手册"],
      "required": true
    },
    {
      "name": "interactive",
      "label": "互动元素",
      "type": "multiselect",
      "options": ["思考题", "讨论环节", "自查清单", "不需要"],
      "required": false
    },
    {
      "name": "speaker_notes",
      "label": "是否生成演讲者逐字稿（按S键可查看）",
      "type": "select",
      "options": ["是", "否"],
      "required": true
    },
    {
      "name": "extra",
      "label": "补充要求（可选，如：多用代码示例、加入真实案例等）",
      "type": "text",
      "required": false
    }
  ]
}
```

### 第二步：检索知识库

使用 `rag_search` 工具，基于培训主题搜索多个关键词，获取全面的文档内容。

### 第四步：生成 HTML

#### HTML 结构

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{培训主题}</title>
  <link rel="stylesheet" href="./assets/base.css">
  <link rel="stylesheet" href="./assets/fonts.css">
  <link rel="stylesheet" id="theme-link" href="./assets/themes/{theme}.css">
  <link rel="stylesheet" href="./assets/animations/animations.css">
</head>
<body>
<div class="deck">
  <section class="slide is-active" id="slide-1">
    <!-- 标题页内容 -->
  </section>
  <section class="slide" id="slide-2">
    <!-- 内容页 -->
  </section>
  <!-- ... -->
</div>
  <script src="./assets/runtime.js"></script>
</body>
</html>
```

#### 幻灯片规范

- 每页一个 `<section class="slide">`，第一页加 `is-active`
- 使用 `data-anim="fade-up"` 添加入场动画
- 列表用 `class="anim-stagger-list"` 实现逐条显示
- 使用 CSS token 变量（`var(--text-1)`, `var(--accent)`等），不写死颜色
- 演讲者备注放在 `<div class="notes">` 内（默认隐藏，按 S 查看）

#### 布局类型与内容限制

| 幻灯片类型 | 最大内容量 | 推荐布局 |
|-----------|-----------|---------|
| 标题页 | 1个标题 + 1个副标题 | title-hero |
| 内容页 | 1个标题 + 4-6个要点 | bullet-list, two-column |
| 卡片页 | 1个标题 + 最多6个卡片(2x3) | card-grid, icon-grid |
| 引用页 | 1段引用(最多3行) + 出处 | quote-centered |
| 总结页 | 1个标题 + 3-5个要点 | summary, cta |

**内容超出限制？拆分为多张幻灯片，绝不压缩。**

如需查看完整布局模板，使用 `load_skill` 加载 `ppt` 技能的 `references/layouts.md`。
如需查看动画效果，使用 `load_skill` 加载 `ppt` 技能的 `references/animations.md`。

### 第五步：保存并产出（必须执行，否则任务未完成）

**必须调用原子脚本保存 HTML，否则用户无法在产出面板看到结果。**

```
terminal(command="python3 ${SKILL_DIR}/scripts/save_and_output.py '<JSON_ARGS>'")
```

参数格式（JSON）：
```json
{
  "workspace_id": "${WORKSPACE_ID}",
  "content": "<生成的完整HTML>",
  "filename": "<safe_topic>.html"
}
```

脚本自动完成：
1. 将 `./assets/` 的 CSS/JS 内联为独立 HTML
2. 保存到 files 目录（`<base_dir>/<workspace_id>/outputs/`）
3. 返回保存路径供确认

**⚠️ 注意：HTML 内容直接写在命令参数中，不要先写到 /tmp！直接传递完整 HTML 给脚本！**

### 第六步：告知用户

保存成功后输出：

---

✅ **PPT 已生成完毕！**

📊 **内容概览：**
- 共 {N} 页幻灯片
- 主题：{theme_name}
- 第1页：标题页 — {培训主题}
- 第2-N页：{简要列出各页核心主题}

⌨️ **快捷键：** ← → 翻页 | T 切换主题 | S 演讲者模式 | F 全屏 | O 总览

📥 请在**右侧产出面板**中查看和下载。

---

## 参考文档（按需加载）

以下参考文档可通过 `load_skill(skill_name="ppt", reference_name="xxx")` 按需加载：

- `references/themes.md` — 36 种主题的详细说明和适用场景
- `references/layouts.md` — 31 种布局模板的使用方法
- `references/animations.md` — 27 CSS + 20 Canvas FX 动画目录
- `references/full-decks.md` — 完整 deck 视觉方向与场景建议
- `references/presenter-mode.md` — 演讲者模式 + 逐字稿编写指南
- `references/authoring-guide.md` — 完整创作工作流

## 键盘快捷键

```
← → Space        翻页
T                 切换主题
S                 演讲者模式
F                 全屏
O                 幻灯片总览
A                 切换动画
N                 笔记抽屉
```

## 严格禁止

- 禁止在对话中输出原始 HTML 代码
- 禁止暴露服务端操作细节、错误信息、文件路径
- 禁止使用技术术语（如「内联CSS/JS」「静态挂载」等）
- 禁止在末尾添加引导性建议
- 保存失败只说「保存遇到问题，请稍后重试」
