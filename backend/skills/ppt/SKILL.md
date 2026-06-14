---
name: ppt
description: Create stunning, animation-rich HTML presentations from scratch or by converting PowerPoint files. Use when the user wants to build a presentation, convert a PPT/PPTX to web, or create slides for a talk/pitch. Helps non-designers discover their aesthetic through visual exploration rather than abstract choices.
---

# Frontend Slides

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

**Question 3 — Content** (header: "Content"):
Do you have content ready? Options: All content ready / Rough notes / Topic only

**Question 4 — Source Documents** (header: "Sources"):
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

**Question 5 — Visual Style** (header: "Style"):
Choose one visual style preset. Options:

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
5. **Confirm via AskUserQuestion** (header: "Outline"): "Does this slide outline and image selection look right?" Options: Looks good / Adjust images / Adjust outline

---

## Phase 2: Build Final Presentation

Generate the final presentation directly using content from Phase 1 (selected documents, text, or text + curated images) and the style preset selected in Phase 1.

Use the selected source documents as the retrieval and generation scope:

- "All documents" means synthesize across all available knowledge-base documents
- Specific document selections mean retrieve from and cite only those selected documents
- If no documents are selected, rely on the user's provided topic, outline, or source content
- Do not imply that unselected documents were used

Do not generate intermediate style previews, do not create `.claude-design/slide-previews/`, and do not ask the user to compare style options after the initial clarification form.

If images were provided, the slide outline already incorporates them from Step 1.2. If not, CSS-generated visuals (gradients, shapes, patterns) provide visual interest — this is a fully supported first-class path.

**Before generating, read these supporting files:**

- [html-template.md](references/html-template.md) — HTML architecture and JS features
- [viewport-base.css](assets/viewport-base.css) — Mandatory CSS (include in full)
- [animation-patterns.md](references/animation-patterns.md) — Animation reference for the selected style and presentation tone

**Key requirements:**

- Single self-contained HTML file, all CSS/JS inline
- Include the FULL contents of viewport-base.css in the `<style>` block
- Use fonts from Fontshare or Google Fonts — never system fonts
- Add detailed comments explaining each section
- Every section needs a clear `/* === SECTION NAME === */` comment block

---

## Phase 3: Delivery

### Step 3.1: Save Output

**You MUST call `save_output` to deliver the presentation.** This is the only way the user can access the result in their output panel.

```
save_output(
  type="ppt",
  title="<presentation title>",
  content="<full self-contained HTML>",
  filename="<safe-filename>.html"
)
```

The HTML must be fully self-contained (all CSS/JS inline). Do NOT use terminal commands or scripts to save — `save_output` is the only delivery mechanism.

### Step 3.2: Confirm to User

Summarize — Tell the user:
   - File location, style name, slide count
   - Navigation: Arrow keys, Space, scroll/swipe, click nav dots
   - How to customize: `:root` CSS variables for colors, font link for typography, `.reveal` class for animations
   - Inline editing: Hover top-left corner or press E to enter edit mode, click any text to edit, Ctrl+S to save

---

## Supporting Files

| File                                               | Purpose                                                              | When to Read              |
| -------------------------------------------------- | -------------------------------------------------------------------- | ------------------------- |
| [style-presets.md](references/style-presets.md)               | 12 curated visual presets with colors, fonts, and signature elements | Phase 2 (generation)      |
| [viewport-base.css](assets/viewport-base.css)             | Mandatory responsive CSS — copy into every presentation              | Phase 2 (generation)      |
| [html-template.md](references/html-template.md)               | HTML structure, JS features, code quality standards                  | Phase 2 (generation)      |
| [animation-patterns.md](references/animation-patterns.md)     | CSS/JS animation snippets and effect-to-feeling guide                | Phase 2 (generation)      |
