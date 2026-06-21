# Style Guide — Cross-Style Universal Rules

These rules apply to **every** presentation regardless of the selected visual style.

---

## Viewport Base CSS

For mandatory base styles, see [viewport-base.css](../assets/viewport-base.css). Include its full contents in every presentation's `<style>` block.

---

## CSS Gotchas

### Negating CSS Functions

**WRONG — silently ignored by browsers (no console error):**
```css
right: -clamp(28px, 3.5vw, 44px);   /* Browser ignores this */
margin-left: -min(10vw, 100px);      /* Browser ignores this */
```

**CORRECT — wrap in `calc()`:**
```css
right: calc(-1 * clamp(28px, 3.5vw, 44px));  /* Works */
margin-left: calc(-1 * min(10vw, 100px));     /* Works */
```

CSS does not allow a leading `-` before function names. The browser silently discards the entire declaration — no error, the element just appears in the wrong position. **Always use `calc(-1 * ...)` to negate CSS function values.**

---

## DO NOT USE (Generic AI Patterns)

**Fonts:** Inter, Roboto, Arial, system fonts as display

**Colors:** `#6366f1` (generic indigo), purple gradients on white

**Layouts:** Everything centered, generic hero sections, identical card grids

**Decorations:** Realistic illustrations, gratuitous glassmorphism, drop shadows without purpose

---

## Font Pairing Quick Reference

All fonts are loaded via `fonts.loli.net` (China-accessible Google Fonts mirror). Never use `fonts.googleapis.com` or `api.fontshare.com` directly.

| Preset | Display Font | Body Font | Source |
|--------|--------------|-----------|--------|
| Bold Signal | Archivo Black | Space Grotesk | fonts.loli.net |
| Electric Studio | Manrope | Manrope | fonts.loli.net |
| Creative Voltage | Syne | Space Mono | fonts.loli.net |
| Dark Botanical | Cormorant | IBM Plex Sans | fonts.loli.net |
| Notebook Tabs | Bodoni Moda | DM Sans | fonts.loli.net |
| Pastel Geometry | Plus Jakarta Sans | Plus Jakarta Sans | fonts.loli.net |
| Split Pastel | Outfit | Outfit | fonts.loli.net |
| Vintage Editorial | Fraunces | Work Sans | fonts.loli.net |
| Neon Cyber | Exo 2 | Space Grotesk | fonts.loli.net |
| Terminal Green | JetBrains Mono | JetBrains Mono | fonts.loli.net |
| Swiss Modern | Archivo | Nunito | fonts.loli.net |
| Paper & Ink | Cormorant Garamond | Source Serif 4 | fonts.loli.net |
