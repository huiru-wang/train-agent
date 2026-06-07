# Authoring guide

How to turn a user request ("make me a deck about X") into a finished,
downloadable HTML deck **in this repository's current workflow**.

## 1. Clarify only what matters

Before generating slides, identify:

1. **Audience** — engineers / managers / new hires / mixed audience
2. **Length** — 5-8 slides / 10-15 slides / 15-20 slides
3. **Tone** — formal / practical / friendly / technical
4. **Format** — live presentation / training material / reference handout
5. **Need speaker notes?** — yes if it is a talk, workshop, or roadshow

## 2. Choose one visual direction

- Theme selection: use `references/themes.md`
- Slide structure: use `references/layouts.md`
- Overall art direction: use `references/full-decks.md`

Do **not** try to open nonexistent local template folders. The current package
ships reference documents plus shared assets, not checked-in example decks.

## 3. Build the outline first

A reliable training deck usually follows:

```text
cover -> agenda -> section divider -> 2-4 body slides ->
section divider -> 2-4 body slides -> summary -> next steps
```

Match slide count to duration:

- 15 minutes: 5-8 slides
- 30 minutes: 10-15 slides
- 60 minutes: 15-20 slides

## 4. Write complete HTML directly

Generate a full HTML document using the standard asset references:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Deck title</title>
  <link rel="stylesheet" href="./assets/base.css">
  <link rel="stylesheet" href="./assets/fonts.css">
  <link rel="stylesheet" id="theme-link" href="./assets/themes/tokyo-night.css">
  <link rel="stylesheet" href="./assets/animations/animations.css">
</head>
<body data-themes="tokyo-night,catppuccin-mocha,corporate-clean">
  <div class="deck">
    <section class="slide is-active" data-title="Cover">
      ...
    </section>
  </div>
  <script src="./assets/runtime.js"></script>
</body>
</html>
```

## 5. Author slide-by-slide

For each slide:

1. Pick one pattern from `references/layouts.md`
2. Keep one main message per slide
3. Add light animation with `data-anim="fade-up"` or `data-anim="rise-in"`
4. Add speaker notes in `.notes` when the deck is intended for live delivery

## 6. Use animations sparingly

- Cover/title: `rise-in`, `blur-in`
- Bullet/content pages: `fade-up`
- Lists/cards: `anim-stagger-list`
- Section divider: `perspective-zoom` or `cube-rotate-3d`
- Closing page: optional stronger accent effect

One hero animation per slide is usually enough.

## 7. Save through the provided script

Do **not** write temp files or invent a second save path. Call:

```bash
python3 ${SKILL_DIR}/scripts/save_and_output.py '<JSON_ARGS>'
```

The script will inline `./assets/*`, save the bundled HTML into the workspace
outputs directory, and return the saved file metadata.

## 8. What not to do

- Do not browse or reference missing `templates/` directories.
- Do not rely on `scripts/new-deck.sh` or `scripts/render.sh`; they are not
  part of the current package.
- Do not expose internal file paths or terminal details to the user.
- Do not put presenter-only narration directly on visible slides.
