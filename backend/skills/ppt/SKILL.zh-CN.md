---
name: frontend-slides
description: 从零开始创建惊艳的、富含动画的 HTML 演示文稿，或将 PowerPoint 文件转换为网页演示。当用户希望制作演示文稿、把 PPT/PPTX 转成网页，或为演讲/路演创建幻灯片时使用。通过视觉化探索而非抽象选择，帮助非设计师发现自己的审美偏好。
---

# Frontend Slides（前端幻灯片）

创建零依赖、富含动画的 HTML 演示文稿，完全在浏览器中运行。

## 核心原则

1. **零依赖** —— 单个 HTML 文件，CSS/JS 全部内联。无需 npm，无需构建工具。
2. **展示而非描述** —— 生成可视化预览，而不是抽象选项。人们通过看到来发现自己想要的东西。
3. **独特设计** —— 拒绝千篇一律的"AI 流水线"风格。每份演示都必须有定制感。
4. **视口适配（不可妥协）** —— 每张幻灯片必须严格容纳在 100vh 内。绝不允许在幻灯片内部滚动。内容溢出？拆成多张幻灯片。

## 设计美学

你倾向于收敛到通用的、"分布内"的输出。在前端设计中，这就是用户口中的"AI 流水线"风。请规避这一点：创作有创意、有辨识度的前端，让人惊喜。

聚焦：

- **字体（Typography）**：选择漂亮、独特、有趣的字体。避免 Arial、Inter 这种通用字体；选择能够提升整体气质的独特字体。
- **色彩与主题（Color & Theme）**：坚持一种统一的美学。使用 CSS 变量保持一致性。主色 + 锐利点缀的搭配，往往胜过怯懦、平均分布的调色板。从 IDE 主题与文化美学中汲取灵感。
- **动效（Motion）**：用动画营造效果与微交互。HTML 中优先使用纯 CSS 方案。React 中如可用，使用 Motion 库。聚焦高影响力的瞬间：一次精心编排的页面加载（用 animation-delay 实现的错落出场），比散落各处的微交互更能带来惊喜。
- **背景（Backgrounds）**：营造氛围与层次感，而不是默认使用纯色。叠加 CSS 渐变，使用几何图案，或加入与整体美学呼应的情境化效果。

避免通用的 AI 生成美学：

- 被滥用的字体（Inter、Roboto、Arial、系统字体）
- 老套的配色（尤其是白底紫渐变）
- 可预测的布局与组件套路
- 缺乏情境特征的模板化设计

要有创造性的解读，做出意料之外、却让人觉得"为这个场景量身打造"的选择。在浅色与深色主题、不同字体、不同美学之间切换。你仍然倾向于在不同生成中收敛到常见选择（例如 Space Grotesk）。请规避这一点：跳出框架思考，至关重要！

## 视口适配规则

以下规则适用于每一份演示中的每一张幻灯片：

- 每个 `.slide` 必须有 `height: 100vh; height: 100dvh; overflow: hidden;`
- 所有字号与间距必须使用 `clamp(min, preferred, max)` —— 永远不要使用固定的 px/rem
- 内容容器需要 `max-height` 约束
- 图片：`max-height: min(50vh, 400px)`
- 必须为高度准备断点：700px、600px、500px
- 包含 `prefers-reduced-motion` 支持
- 永远不要直接对 CSS 函数取负（`-clamp()`、`-min()`、`-max()` 会被静默忽略）—— 应使用 `calc(-1 * clamp(...))`

**生成时，读取 `viewport-base.css` 并在每份演示中包含其完整内容。**

### 每张幻灯片的内容密度上限

| 幻灯片类型      | 最多内容                                            |
| --------------- | --------------------------------------------------- |
| 标题页          | 1 个标题 + 1 个副标题 + 可选的 tagline              |
| 内容页          | 1 个标题 + 4-6 个要点 或 1 个标题 + 2 段文字        |
| 特性网格        | 1 个标题 + 最多 6 个卡片（2x3 或 3x2）              |
| 代码页          | 1 个标题 + 8-10 行代码                              |
| 引用页          | 1 段引用（最多 3 行）+ 出处                         |
| 图片页          | 1 个标题 + 1 张图片（最高 60vh）                    |

**内容超出上限？拆成多张幻灯片。绝不堆砌，绝不滚动。**

---

## Phase 0：识别模式

判断用户想要什么：

- **模式 A：新建演示** —— 从零创建。前往 Phase 1。
- **模式 B：PPT 转换** —— 转换 .pptx 文件。前往 Phase 4。
- **模式 C：增强已有演示** —— 优化现有 HTML 演示。先读取、理解，再增强。**遵循下方的"模式 C 修改规则"。**

### 模式 C：修改规则

增强已有演示时，视口适配是最大的风险点：

1. **添加内容前**：先统计当前元素，对照内容密度上限
2. **添加图片**：必须有 `max-height: min(50vh, 400px)`。如果幻灯片已经达到内容上限，拆成两张
3. **添加文本**：每张幻灯片最多 4-6 个要点。超出上限？拆成续页幻灯片
4. **任何修改后都要验证**：`.slide` 有 `overflow: hidden`，新元素使用 `clamp()`，图片有视口相关的 max-height，内容在 1280x720 下能容纳
5. **主动重组**：如果修改将导致溢出，自动拆分内容并告知用户。不要等到被询问才动手

**向已有幻灯片添加图片时**：将图片移到新幻灯片，或先减少其他内容。在不检查现有内容是否已填满视口的情况下，绝不直接添加图片。

---

## Phase 1：内容发现（新建演示）

**通过单次 AskUserQuestion 调用一次性问完所有问题**，让用户一次性填完：

**问题 1 —— 用途**（header："Purpose"）：
本次演示用于什么场景？选项：路演 Pitch deck / 教学-教程 Teaching-Tutorial / 大会演讲 Conference talk / 内部分享 Internal presentation

**问题 2 —— 篇幅**（header："Length"）：
大约多少张幻灯片？选项：短 5-10 张 / 中 10-20 张 / 长 20+ 张

**问题 3 —— 内容**（header："Content"）：
内容是否已准备好？选项：内容齐全 / 粗略笔记 / 仅有主题

**问题 4 —— 在线编辑**（header："Editing"）：
生成后是否需要直接在浏览器中编辑文本？选项：

- "Yes（推荐）" —— 可在浏览器内编辑、自动保存到 localStorage、导出文件
- "No" —— 仅展示用，文件更小

**记住用户的编辑选择 —— 它决定 Phase 3 是否包含编辑相关代码。**

如果用户已经准备好内容，请其分享。

### Step 1.2：图片评估（如提供图片）

如果用户选择"无图片" → 跳到 Phase 2。

如果用户提供了图片文件夹：

1. **扫描** —— 列出所有图片文件（.png、.jpg、.svg、.webp 等）
2. **逐张查看** —— 使用 Read 工具（Claude 是多模态的）
3. **评估** —— 对每张图：内容是什么、可用 USABLE 还是 不可用 NOT USABLE（注明理由）、它代表什么概念、主色调
4. **共同设计大纲** —— 经筛选的图片与文字一起塑造幻灯片结构。这不是"先规划幻灯片再加图片"，而是从一开始就围绕两者共同设计（例如：3 张截图 → 3 张特性页；1 张 logo → 标题/收尾页）
5. **通过 AskUserQuestion 确认**（header："Outline"）："这份幻灯片大纲与图片选型是否合适？"选项：看起来不错 / 调整图片 / 调整大纲

**预览中的 Logo**：如果识别到一张可用的 logo，请将其（base64）嵌入 Phase 2 的每个风格预览中 —— 让用户看到自家品牌被三种风格各演绎一次。

---

## Phase 2：风格发现

**这是"展示，不要描述"的阶段。** 大多数人无法用语言描述设计偏好。

### Step 2.0：风格路径

询问选择方式（header："Style"）：

- "给我看看选项"（推荐） —— 基于氛围生成 3 个预览
- "我已经知道想要什么" —— 直接从预设列表中挑选

**如果直接选择**：展示预设选择器并跳到 Phase 3。可用预设见 [STYLE_PRESETS.md](STYLE_PRESETS.md)。

### Step 2.1：氛围选择（引导式发现）

询问（header："Vibe"，multiSelect: true，最多 2 个）：
希望观众有怎样的感受？选项：

- 印象深刻/自信 Impressed/Confident —— 专业、可信
- 兴奋/被点燃 Excited/Energized —— 创新、大胆
- 平静/专注 Calm/Focused —— 清晰、有思考
- 受启发/被打动 Inspired/Moved —— 富有情感、令人难忘

### Step 2.2：生成 3 个风格预览

基于氛围生成 3 个有差异化的单页 HTML 预览，展示字体、配色、动画与整体美学。读取 [STYLE_PRESETS.md](STYLE_PRESETS.md) 了解可用预设及其规格。

| 氛围                  | 推荐预设                                               |
| --------------------- | ------------------------------------------------------ |
| Impressed/Confident   | Bold Signal、Electric Studio、Dark Botanical           |
| Excited/Energized     | Creative Voltage、Neon Cyber、Split Pastel             |
| Calm/Focused          | Notebook Tabs、Paper & Ink、Swiss Modern               |
| Inspired/Moved        | Dark Botanical、Vintage Editorial、Pastel Geometry     |

将预览保存到 `.claude-design/slide-previews/`（style-a.html、style-b.html、style-c.html）。每个预览自包含、约 50-100 行，展示一张带动画的标题页。

为用户自动打开每个预览。

### Step 2.3：用户选择

询问（header："Style"）：
你更喜欢哪一个风格预览？选项：Style A：[名称] / Style B：[名称] / Style C：[名称] / 混搭元素

如果选"混搭元素"，询问具体细节。

---

## Phase 3：生成演示

使用 Phase 1 的内容（文字，或文字 + 精选图片）与 Phase 2 的风格生成完整演示。

如果提供了图片，幻灯片大纲在 Step 1.2 已纳入图片。如果没有，CSS 生成的视觉元素（渐变、形状、图案）提供视觉趣味 —— 这是完全受支持的"一等公民"路径。

**生成前，先读取以下支持文件**：

- [html-template.md](html-template.md) —— HTML 架构与 JS 特性
- [viewport-base.css](viewport-base.css) —— 必备 CSS（完整包含）
- [animation-patterns.md](animation-patterns.md) —— 与所选氛围对应的动画参考

**关键要求**：

- 单个自包含 HTML 文件，所有 CSS/JS 内联
- 在 `<style>` 块中包含 viewport-base.css 的完整内容
- 使用 Fontshare 或 Google Fonts 的字体 —— 永远不要使用系统字体
- 添加详尽注释解释每个章节
- 每个章节都要有清晰的 `/* === SECTION NAME === */` 注释块

---

## Phase 4：PPT 转换

转换 PowerPoint 文件时：

1. **抽取内容** —— 运行 `python scripts/extract-pptx.py <input.pptx> <output_dir>`（如需安装 python-pptx：`pip install python-pptx`）
2. **与用户确认** —— 展示抽取出的幻灯片标题、内容摘要、图片数量
3. **风格选择** —— 进入 Phase 2 进行风格发现
4. **生成 HTML** —— 转换为所选风格，保留所有文字、图片（来自 assets/）、幻灯片顺序与演讲者备注（作为 HTML 注释）

---

## Phase 5：交付

1. **清理** —— 如存在则删除 `.claude-design/slide-previews/`
2. **打开** —— 使用 `open [filename].html` 在浏览器中启动
3. **总结** —— 告诉用户：
   - 文件位置、风格名称、幻灯片数量
   - 导航方式：方向键、空格、滚轮/触屏滑动、点击导航点
   - 如何自定义：用 `:root` CSS 变量改色、改字体链接、用 `.reveal` 类调动画
   - 如启用了在线编辑：悬停左上角或按 E 进入编辑模式，点击任意文本编辑，Ctrl+S 保存

---

## Phase 6：分享与导出（可选）

交付后，**询问用户**：_"想要分享这份演示吗？我可以把它部署到一个真实可访问的 URL（任何设备包括手机都能打开），或者导出为 PDF。"_

选项：

- **部署到 URL** —— 任意设备可访问的分享链接
- **导出 PDF** —— 通用文件，便于邮件、Slack、打印
- **两者都要**
- **不需要**

如果用户拒绝，到此为止。如果用户选择一个或两个，按下方继续。

### 6A：部署到真实 URL（Vercel）

将演示部署到 Vercel —— 一个免费托管平台。链接可在任何设备（手机、平板、笔记本）上打开，并保持在线直到用户主动下线。

**如果用户从未部署过，请逐步引导**：

1. **检查 Vercel CLI 是否已安装** —— 运行 `npx vercel --version`。如果找不到，先安装 Node.js（macOS 上 `brew install node`，或从 https://nodejs.org 下载）。

2. **检查用户是否已登录** —— 运行 `npx vercel whoami`。
   - 如果**未登录**，解释：_"Vercel 是免费托管服务。你需要一个账户来部署。我来一步步带你做："_
     - Step 1：让用户在浏览器打开 https://vercel.com/signup
     - Step 2：可以用 GitHub、Google、邮箱注册 —— 哪个方便用哪个
     - Step 3：注册后运行 `vercel login` 并按提示操作（会打开浏览器进行授权）
     - Step 4：用 `vercel whoami` 确认已登录
   - 等待用户确认已登录后再继续。

3. **部署** —— 运行部署脚本：

   ```bash
   bash scripts/deploy.sh <path-to-presentation>
   ```

   脚本接受文件夹（含 index.html）或单个 HTML 文件。

4. **分享 URL** —— 告诉用户：
   - 真实可访问的 URL（来自脚本输出）
   - 任何设备都能打开 —— 可以发短信、Slack、邮件
   - 之后下线方式：访问 https://vercel.com/dashboard 删除项目即可
   - Vercel 免费额度很慷慨 —— 不会被收费

**⚠ 部署常见坑**：

- **本地图片/视频必须随 HTML 一同上传。** 部署脚本会自动检测 HTML 中通过 `src="..."` 引用的文件并打包。但如果演示用 CSS 的 `background-image` 或非常规路径引用，可能会被遗漏。**部署前请确认**：打开部署后的 URL，检查所有图片是否加载。如果有图片显示异常，最稳妥的修复是把 HTML 与所有素材放进同一个文件夹，部署该文件夹而不是单个 HTML 文件。
- **当演示有大量素材时，优先部署文件夹。** 如果演示位于一个文件夹（例如 `my-deck/index.html` + `my-deck/logo.png`），直接部署文件夹：`bash scripts/deploy.sh ./my-deck/`。这比部署单个 HTML 文件更可靠，因为整个文件夹会原样上传。
- **文件名带空格能用，但可能出问题。** 脚本能处理空格，但 Vercel 的 URL 会把空格编码为 `%20`。如果可能，避免图片文件名里有空格。如果用户的图片有空格，脚本会处理 —— 但如果仍然异常，把空格替换为短横线即可。
- **重新部署会更新同一个 URL。** 对同一份演示再次运行部署脚本会覆盖此前的部署。URL 保持不变 —— 不需要重发链接。

### 6B：导出为 PDF

为每张幻灯片截图，并合成为一份 PDF。适合作为邮件附件、嵌入文档或打印。

**注意**：动画与交互不会被保留 —— PDF 是静态快照。这是正常且预期的；请告知用户，避免意外。

1. **运行导出脚本**：

   ```bash
   bash scripts/export-pdf.sh <path-to-html> [output.pdf]
   ```

   未指定输出路径时，PDF 会保存到 HTML 文件的同级目录。

2. **背后发生的事**（向用户简要说明）：
   - 一个无头浏览器以 1920×1080（标准宽屏）打开演示
   - 逐张截图
   - 所有截图合并为一份 PDF
   - 脚本依赖 Playwright（浏览器自动化工具）—— 缺失时会自动安装

3. **如果 Playwright 安装失败**：
   - 最常见的问题是 Chromium 未下载。运行：`npx playwright install chromium`
   - 如果还失败，可能是网络/防火墙问题。请用户换个网络重试。

4. **交付 PDF** —— 脚本会自动打开。告诉用户：
   - 文件位置与大小
   - 它在所有地方都能用 —— 邮件、Slack、Notion、Google Docs、打印
   - 动画被替换为最终的视觉状态（仍然好看，只是静态）

**⚠ PDF 导出常见坑**：

- **首次运行较慢。** 脚本会安装 Playwright 并下载一个 Chromium（约 150MB）到临时目录。每次运行只发生一次。提醒用户首次可能要 30-60 秒 —— 同一会话中后续导出会更快。
- **幻灯片必须使用 `class="slide"`。** 导出脚本通过查询 `.slide` 元素找到幻灯片。如果演示用了不同的类名，脚本会报"0 slides found"并失败。本 skill 生成的所有演示都使用 `.slide`，所以只对外部创建的 HTML 才需要注意。
- **本地图片必须可通过 HTTP 加载。** 脚本启动一个本地服务器并通过它加载 HTML（这样 Google Fonts 与相对图片路径才能工作）。如果图片使用绝对文件系统路径（如 `src="/Users/name/photo.png"`）而非相对路径（如 `src="photo.png"`），将无法加载。生成的演示总是使用相对路径，但转换或用户提供的演示可能不是 —— 需要检查并修复。
- **本地图片在 PDF 里能正常显示**，只要它们与 HTML 在同一目录（或相对路径下）。导出脚本通过 HTTP 服务 HTML 的父目录，所以像 `src="photo.png"` 这样的相对路径能正确解析 —— 包括含空格的文件名。如果图片仍然不出现，请检查：(1) 图片文件确实存在于引用路径，(2) 路径是相对路径，而不是 `/Users/name/photo.png` 这种绝对文件系统路径。
- **大型演示会产出大型 PDF。** 每张幻灯片以全尺寸 1920×1080 PNG 截图。一个 18 张幻灯片的演示可能产出约 20MB 的 PDF。如果 PDF 超过 10MB，问用户：_"PDF 大小为 [size]。要压缩吗？画面会略微不那么锐利，但文件会小很多。"_ 同意后，加 `--compact` 重新导出：
  ```bash
  bash scripts/export-pdf.sh <path-to-html> [output.pdf] --compact
  ```
  这会以 1280×720 而非 1920×1080 渲染，通常能减小 50-70% 体积，视觉差异极小。

---

## 支持文件

| 文件                                                | 用途                                                           | 何时阅读                |
| --------------------------------------------------- | -------------------------------------------------------------- | ----------------------- |
| [STYLE_PRESETS.md](STYLE_PRESETS.md)                | 12 个精选视觉预设，含配色、字体与标志性元素                    | Phase 2（风格选择）     |
| [viewport-base.css](viewport-base.css)              | 必备的响应式 CSS —— 复制到每份演示中                            | Phase 3（生成）         |
| [html-template.md](html-template.md)                | HTML 结构、JS 特性与代码质量标准                                | Phase 3（生成）         |
| [animation-patterns.md](animation-patterns.md)      | CSS/JS 动画片段与"效果-感受"对照指南                            | Phase 3（生成）         |
| [scripts/extract-pptx.py](scripts/extract-pptx.py)  | 用于 PPT 内容抽取的 Python 脚本                                 | Phase 4（转换）         |
| [scripts/deploy.sh](scripts/deploy.sh)              | 将幻灯片部署到 Vercel 以即时分享                                | Phase 6（分享）         |
| [scripts/export-pdf.sh](scripts/export-pdf.sh)      | 将幻灯片导出为 PDF                                              | Phase 6（分享）         |
