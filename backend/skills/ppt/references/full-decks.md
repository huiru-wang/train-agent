# Full-Deck Directions

The current skill package does **not** include checked-in full-deck HTML
templates. Use this document as an **art-direction catalog**: pick one visual
direction, then implement the deck directly in the generated HTML.

## Recommended deck archetypes

| direction | feel | best for |
|---|---|---|
| `xhs-white-editorial` | White background, magazine hierarchy, colorful accents | Knowledge cards, consumer-facing training, Chinese-first decks |
| `graphify-dark-graph` | Deep dark background, graph / AI / data atmosphere | Tooling, RAG, knowledge graph, infra topics |
| `knowledge-arch-blueprint` | Cream paper, engineering blueprint, structured diagrams | Architecture, workflows, technical design |
| `hermes-cyber-terminal` | Terminal-like, mono typography, dark review aesthetic | CLI, agent, benchmark, debugging talks |
| `obsidian-claude-gradient` | GitHub-dark with purple-blue gradients | Dev workflow, API, MCP, AI tooling |
| `testing-safety-alert` | Red / amber warning language, high seriousness | Safety, risk, review, incident, compliance |
| `xhs-pastel-card` | Soft pastel cards, lifestyle-friendly | Soft onboarding, non-technical education, light storytelling |
| `dir-key-nav-minimal` | Minimal keynote, big statements, generous whitespace | Talks, keynotes, single-idea slides |

## Generic reusable scenarios

| scenario | default direction | notes |
|---|---|---|
| Fundraising / business pitch | `pitch-deck-vc` theme + `kpi-grid` / `two-column` layouts | Prioritize metrics and differentiation |
| Product launch | `glassmorphism` or `aurora` | Strong cover, feature cards, CTA close |
| Technical sharing | `tokyo-night`, `catppuccin-mocha`, or `blueprint` | Use examples, diagrams, and summary slides |
| Weekly report | `corporate-clean` or `arctic-cool` | Lean on tables, KPI grids, and next-step slides |
| Teaching / workshop | `academic-paper`, `minimal-white`, or `soft-pastel` | Add checklists, recap slides, and speaker notes |

## How to use this catalog

1. Pick **one** direction for the whole deck.
2. Pair it with a theme from `references/themes.md`.
3. Build the slide sequence using `references/layouts.md`.
4. Keep the tone consistent instead of mixing multiple art directions.

If the user asks for a specific named template, translate that request into one
of the directions above instead of trying to open a missing local HTML file.
