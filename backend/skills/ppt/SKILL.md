---
name: html-ppt
description: Create stunning, animation-rich HTML presentations from scratch or by converting PowerPoint files. Use when the user wants to build a presentation, convert a PPT/PPTX to web, or create slides for a talk/pitch. Helps non-designers discover their aesthetic through visual exploration rather than abstract choices.
---

# html-ppt

Create zero-dependency, animation-rich HTML presentations that run entirely in the browser.

## Core Principles

1. **Zero Dependencies** — Single HTML files with inline CSS/JS. No npm, no build tools.
2. **Single-step choices** — Collect concrete choices up front, then generate the final deliverable directly. Do not create intermediate style preview files.
3. **Distinctive Design** — No generic "AI slop." Every presentation must feel custom-crafted.
4. **Viewport Fitting (NON-NEGOTIABLE)** — Every slide MUST fit exactly within 100vh. No scrolling within slides, ever. Content overflows? Split into multiple slides.

## Design Aesthetics

You tend to converge toward generic, "on distribution" outputs. In frontend design, this creates what users call the "AI slop" aesthetic. Avoid this: make creative, distinctive frontends that surprise and delight.

Focus on:

- Typography: Choose fonts that are beautiful, unique, and interesting. Avoid generic fonts like Arial and Inter; opt instead for distinctive choices that elevate the frontend's aesthetics.
- Color & Theme: Commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with sharp accents outperform timid, evenly-distributed palettes. Draw from IDE themes and cultural aesthetics for inspiration.
- Motion: Use animations for effects and micro-interactions. Prioritize CSS-only solutions for HTML. Use Motion library for React when available. Focus on high-impact moments: one well-orchestrated page load with staggered reveals (animation-delay) creates more delight than scattered micro-interactions.
- Backgrounds: Create atmosphere and depth rather than defaulting to solid colors. Layer CSS gradients, use geometric patterns, or add contextual effects that match the overall aesthetic.

Avoid generic AI-generated aesthetics:

- Overused font families (Inter, Roboto, Arial, system fonts)
- Cliched color schemes (particularly purple gradients on white backgrounds)
- Predictable layouts and component patterns
- Cookie-cutter design that lacks context-specific character

Interpret creatively and make unexpected choices that feel genuinely designed for the context. Vary between light and dark themes, different fonts, different aesthetics. You still tend to converge on common choices (Space Grotesk, for example) across generations. Avoid this: it is critical that you think outside the box!

## Viewport Fitting Rules

These invariants apply to EVERY slide in EVERY presentation:

- Every `.slide` must have `height: 100vh; height: 100dvh; overflow: hidden;`
- ALL font sizes and spacing must use `clamp(min, preferred, max)` — never fixed px/rem
- Content containers need `max-height` constraints
- Images: `max-height: min(50vh, 400px)`
- Breakpoints required for heights: 700px, 600px, 500px
- Include `prefers-reduced-motion` support
- Never negate CSS functions directly (`-clamp()`, `-min()`, `-max()` are silently ignored) — use `calc(-1 * clamp(...))` instead

**When generating, read `viewport-base.css` and include its full contents in every presentation.**

### Content Density Limits Per Slide

| Slide Type    | Maximum Content                                           |
| ------------- | --------------------------------------------------------- |
| Title slide   | 1 heading + 1 subtitle + optional tagline                 |
| Content slide | 1 heading + 4-6 bullet points OR 1 heading + 2 paragraphs |
| Feature grid  | 1 heading + 6 cards maximum (2x3 or 3x2)                  |
| Code slide    | 1 heading + 8-10 lines of code                            |
| Quote slide   | 1 quote (max 3 lines) + attribution                       |
| Image slide   | 1 heading + 1 image (max 60vh height)                     |

**Content exceeds limits? Split into multiple slides. Never cram, never scroll.**

---

## Phase 1: Content Discovery

**Ask ALL questions in a single AskUserQuestion call** so the user fills everything out at once:

**Question 1 — Purpose** (header: "Purpose"):
What is this presentation for? Options: Pitch deck / Teaching-Tutorial / Conference talk / Internal presentation

**Question 2 — Length** (header: "Length"):
Approximately how many slides? Options: Short 5-10 / Medium 10-20 / Long 20+

**Question 3 — Source Documents** (header: "Sources"):
Before asking Phase 1 questions, inspect the knowledge-base document summaries injected in the system prompt.

If one or more documents are available, include a multiselect `source_documents` field:

- List every available document by filename or clear title
- Include "All documents (Recommended)" as the default/recommended option
- If the user selects "All documents", use every available knowledge-base document
- If the user selects specific documents, use only those documents as the generation scope
- If the user selects both "All documents" and specific documents, treat "All documents" as authoritative

If no knowledge-base documents are available, do not show `source_documents`. Instead include a required text field:

- name: `topic_or_outline`
- label: "Topic / Outline"
- description: "No knowledge-base documents are available. Provide the PPT topic, target content, or outline."

Do not proceed with PPT generation when there are no documents and the user has not provided a concrete topic, outline, or source content.

**Question 4 — Visual Style** (header: "Style"):
If the system prompt contains a "用户配置偏好" section with a PPT visual style already selected, **skip this question entirely** and use the pre-selected style directly. Do not ask the user to choose a style again.

If no pre-selected style is available, ask the user to choose. Options:

- Swiss Modern (Recommended) — Minimal, precise, ideal for technical training and structured explanations
- Bold Signal — Dark, high-impact, strong emphasis
- Electric Studio — Blue/white, professional, polished
- Creative Voltage — Energetic, creative, product/innovation friendly
- Dark Botanical — Elegant, premium, atmospheric
- Notebook Tabs — Editorial paper/tabs, organized course feel
- Pastel Geometry — Soft, modern, approachable
- Split Pastel — Playful, friendly, beginner-friendly
- Vintage Editorial — Opinionated editorial, distinctive personality
- Neon Cyber — Futuristic, tech-forward, AI/cyber feel
- Terminal Green — Engineering, code-heavy, terminal-inspired
- Paper & Ink — Thoughtful paper texture, deep explanation

If the user does not choose a style, default to Swiss Modern.

**Default capability — Inline Editing**:
Do not ask whether inline editing is needed. Generated HTML presentations must support editing text directly in the browser by default, including edit mode, localStorage auto-save, and export/save functionality.

Only disable inline editing when the user explicitly asks for a presentation-only file, a smaller file, or no editing controls.

If user has content, ask them to share it. If the user selected "I will provide a topic or outline instead", ask them to provide it before continuing.

### Step 1.2: Image Evaluation (if images provided)

If user selected "No images" → skip to Phase 2.

If user provides an image folder:

1. **Scan** — List all image files (.png, .jpg, .svg, .webp, etc.)
2. **View each image** — Use the Read tool (Claude is multimodal)
3. **Evaluate** — For each: what it shows, USABLE or NOT USABLE (with reason), what concept it represents, dominant colors
4. **Co-design the outline** — Curated images inform slide structure alongside text. This is NOT "plan slides then add images" — design around both from the start (e.g., 3 screenshots → 3 feature slides, 1 logo → title/closing slide)
5. Use the image evaluation to inform the text outline in Phase 2.

---

## Phase 2: Outline Confirmation

Before generating the final HTML presentation, create a text-only Markdown outline and ask the user to confirm it.

**Hard gate:** Do not generate the full HTML presentation and do not call `save_ppt` until the user explicitly confirms the outline.

Use the selected source documents as the retrieval and generation scope:

- "All documents" means synthesize across all available knowledge-base documents
- Specific document selections mean retrieve from and cite only those selected documents
- If no documents are selected, rely on the user's provided topic, outline, or source content
- Do not imply that unselected documents were used

Do not generate intermediate style previews, do not create `.claude-design/slide-previews/`, and do not ask the user to compare style options after the initial clarification form.

If images were provided, incorporate the selected usable images into the outline. If not, plan CSS-generated visuals (gradients, shapes, patterns) as first-class visual elements.

### Step 2.1: Draft Outline

Output the outline as Markdown in this structure:

```md
## PPT 大纲确认

主题：...
目标受众：...
用途：...
预计页数：...
视觉风格：...
内容来源：...

### 幻灯片结构

| # | 标题 | 核心内容 | 关键词 | 视觉建议 | 依据/来源 |
|---|------|----------|--------|----------|-----------|
| 1 | ... | ... | 关键词1,关键词2,关键词3 | ... | ... |
| 2 | ... | ... | 关键词1,关键词2,关键词3 | ... | ... |

### 内容取舍说明

- 会重点展开：...
- 会简略处理：...
- 暂不纳入：...

### 请确认

如果这个大纲方向没问题，请回复“确认”。
如果需要调整，请直接说明希望修改的部分，例如：增加/删除章节、调整页数、更换顺序、加强案例、加强代码、加强图解或总结。
```

#### Keywords 生成规则（重要）

`keywords` 的唯一用途是作为 RAG 检索查询词，从知识库原始文档中召回与该幻灯片相关的段落。生成时必须遵守以下规则：

**✅ 必须包含：**
- 该幻灯片涉及的**具体技术术语、专有名词、API/类名**（如 `ThreadPoolExecutor`、`volatile`、`CountDownLatch`）
- 该幻灯片涉及的**具体业务场景或操作名称**（如 "加锁顺序"、"死锁预防"、"线程池配置参数"）
- 优先选择**在源文档原文中出现过的词汇**，以提高向量检索的召回率

**❌ 禁止包含：**
- **文档来源/出版方名称**：如 "阿里巴巴"、"Oracle"、"IBM"（这些不是文档内容本身，检索不到有用段落）
- **元描述词/篇章结构词**：如 "总结"、"回顾"、"概述"、"最佳实践"、"要点"（这些词不出现在原文中，检索结果为空）
- **过于宽泛的通用词**：如 "Java"、"规范"、"编程"、"并发"（单独使用区分度太低，检索噪声大）

**示例对比：**

| 幻灯片 | ❌ 错误 keywords | ✅ 正确 keywords |
|--------|----------------|----------------|
| 封面/标题 | 阿里巴巴, Java, 并发, 规范 | 并发处理, 编程规约, 线程安全规范 |
| 核心要点回顾 | 总结, 回顾, 最佳实践 | ThreadPoolExecutor, 锁粒度, volatile, ConcurrentHashMap |

Keep the outline concise but concrete enough for the user to judge scope, order, and emphasis. Do not call tools in the same assistant message as the outline unless retrieval is needed before writing it.

### Step 2.2: Multi-turn Revision Loop

After presenting the outline, wait for the user's reply.

- If the user explicitly confirms, proceed to Phase 3.
- If the user asks for changes, revise the outline and ask for confirmation again.
- If the user reply is ambiguous, ask one short confirmation question before proceeding.
- If the requested change conflicts with selected documents or available evidence, explain the tradeoff and propose a revised outline for confirmation.

Explicit confirmations include: "确认", "可以", "没问题", "按这个来", "开始生成", "Looks good", "Approved", or equivalent clear approval.

During this loop:

- Do not generate the full HTML presentation.
- Do not call `save_ppt`.
- Do not claim the PPT is complete.
- Preserve the latest confirmed outline as the source of truth for final generation.

---

## Phase 3: Build Final Presentation

Generate the final presentation using the last outline explicitly confirmed by the user.

The final presentation must follow the confirmed outline. You may split an overloaded slide into multiple slides for viewport fitting, but do not add or remove major sections without asking the user to confirm an updated outline.

**Before generating, read these supporting files:**

- [html-template.md](references/html-template.md) — HTML architecture and JS features
- [style-presets.md](references/style-presets.md) — Detailed visual preset guidance
- [viewport-base.css](assets/viewport-base.css) — Mandatory CSS (include in full)
- [animation-patterns.md](references/animation-patterns.md) — Animation reference for the selected style and presentation tone

**Key requirements:**

- Single self-contained HTML file, all CSS/JS inline
- Include the FULL contents of viewport-base.css in the `<style>` block
- Use fonts from Fontshare or Google Fonts — never system fonts
- Add detailed comments explaining each section
- Every section needs a clear `/* === SECTION NAME === */` comment block

---

## Phase 4: Delivery

### Step 4.1: Save Output

**You MUST call `save_ppt` to deliver the presentation, but only after the user has explicitly confirmed the outline and the final HTML is complete.** This is the only way the user can access the result in their output panel.

Never call `save_ppt` during outline drafting, outline revision, or before explicit user approval.

```
save_ppt(
  title="<presentation title, 不超过20个字>",
  content="<full self-contained HTML>",
  filename="<safe-filename>.html",
  outline=<JSON string of structured outline>
)
```

**`title` 命名规则**：标题必须简洁，**不超过 20 个字**。超出时应精简为核心主题（如“并发编程规范精讲”而非“阿里巴巴Java开发手册之并发编程规范精讲”）。

The `outline` parameter must be a JSON string matching this schema:
```json
{
  "title": "PPT主题",
  "topic": "PPT的核心主题（简短，如：并发编程规范、消防安全培训）",
  "summary": "PPT的全局摘要（2-3句话概括整个PPT的核心内容和目标）",
  "audience": "目标受众",
  "purpose": "用途",
  "total_slides": 12,
  "style": "swiss-modern",
  "slides": [
    {
      "number": 1,
      "title": "幻灯片标题",
      "key_points": ["要点1", "要点2"],
      "keywords": ["关键词1", "关键词2", "关键词3"],
      "source_refs": ["doc_id:xxx"],
      "notes": "补充说明（可选）"
    }
  ]
}
```

**`topic`** 是 PPT 的核心主题，简短明了（如"并发编程规范"、"新员工入职安全培训"）。
**`summary`** 用 2-3 句话概括整个 PPT 的核心内容、目标和价值，用于后续口播稿生成和系统提示展示。

This outline is used later for narration generation and RAG retrieval.

**`keywords` 规则（强制执行）：**
- 每张幻灯片填写 **3-6 个关键词**
- 关键词必须能作为 RAG 查询词，从知识库原文中召回与该页相关的段落
- 只填写**具体的技术术语、专有名词、API/类名、业务场景词**，且优先使用源文档原文中出现过的词汇
- **禁止**填写：文档来源/出版方名（如"阿里巴巴"）、元描述词（如"总结"、"回顾"、"概述"、"最佳实践"）、过于宽泛的通用词（如单独写"Java"、"规范"）
- 封面页和总结页同样需要填写与该页实际内容对应的具体术语，不得使用篇章结构词

The HTML must be fully self-contained (all CSS/JS inline). Do NOT use terminal commands or scripts to save — `save_ppt` is the only delivery mechanism.

### Step 4.2: Confirm to User

Summarize — Tell the user:
   - File location, style name, slide count
   - Navigation: Arrow keys, Space, scroll/swipe, click nav dots
   - How to customize: `:root` CSS variables for colors, font link for typography, `.reveal` class for animations
   - Inline editing: Hover top-left corner or press E to enter edit mode, click any text to edit, Ctrl+S to save

---

## Supporting Files

| File                                               | Purpose                                                              | When to Read              |
| -------------------------------------------------- | -------------------------------------------------------------------- | ------------------------- |
| [style-presets.md](references/style-presets.md)               | 12 curated visual presets with colors, fonts, and signature elements | Phase 3 (generation)      |
| [viewport-base.css](assets/viewport-base.css)             | Mandatory responsive CSS — copy into every presentation              | Phase 3 (generation)      |
| [html-template.md](references/html-template.md)               | HTML structure, JS features, code quality standards                  | Phase 3 (generation)      |
| [animation-patterns.md](references/animation-patterns.md)     | CSS/JS animation snippets and effect-to-feeling guide                | Phase 3 (generation)      |
