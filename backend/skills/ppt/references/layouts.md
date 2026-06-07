# Layouts catalog

This repository does **not** ship browsable `templates/single-page/*.html`
files. Treat this document as a layout decision guide, then write the final
`<section class="slide">...</section>` blocks directly in the generated deck.

Each slide should stay within one clear layout pattern. If the content does not
fit, split it into multiple slides instead of compressing typography.

## Openers & navigation

| pattern | when to use | recommended structure |
|---|---|---|
| `cover` | Title page, opening promise | eyebrow + large title + subtitle + 2-4 topic pills |
| `toc` | Agenda / course outline | title + 4-6 numbered cards |
| `section-divider` | Start of a new chapter | section number + short chapter name + one-sentence transition |

## Text-centric slides

| pattern | when to use | recommended structure |
|---|---|---|
| `bullet-list` | Explain 4-6 key ideas | title + concise bullet list |
| `two-column` | Concept vs example / before vs after | title + left/right comparison |
| `three-column` | Parallel categories | title + 3 equally weighted cards |
| `quote-centered` | Principle / memorable sentence | quote + attribution or takeaway |

## Data & structure

| pattern | when to use | recommended structure |
|---|---|---|
| `kpi-grid` | 3-4 numbers or metrics | title + 3-4 stat cards |
| `table` | Structured comparison | title + compact table + one takeaway line |
| `process-flow` | Ordered steps | title + 3-6 connected steps |
| `matrix` | 2x2 categorization | title + quadrant labels + short annotations |

## Training-friendly slides

| pattern | when to use | recommended structure |
|---|---|---|
| `concept-cards` | Vocabulary / feature clusters | title + 4-6 concept cards |
| `example-breakdown` | Code / scenario walk-through | title + example block + annotated points |
| `checklist` | Actionable guidance | title + yes/no or do/don't checklist |
| `summary` | Recap page | title + 3-5 key reminders |

## Authoring rules

- Keep one main message per slide.
- Prefer `data-anim="fade-up"` or `data-anim="rise-in"` on the headline element.
- Use `class="anim-stagger-list"` for lists or card grids that should reveal
  item-by-item.
- Put speaker notes in `<div class="notes">...</div>` or
  `<aside class="notes">...</aside>`.
- Use CSS tokens from the theme; do not hardcode palette values unless a visual
  accent is truly necessary.
