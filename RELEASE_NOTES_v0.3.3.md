# astrbot_plugin_mhhelper v0.3.3

The QQ image cards were **blurry, with everything crammed into the top-left
corner**. Fixed by rebuilding the card template against what AstrBot's 文转图
actually does — and by overriding its default JPEG quality.

## What was wrong

The card template was a shrink-wrapped `display: inline-block` box capped at
920px, with a 15px base font:

```css
.card { display: inline-block; max-width: 920px; }
body  { font-size: 15px; }
```

AstrBot's renderer (`NetworkRenderStrategy.render_custom_template`) screenshots
a **full page in an ~800×615 viewport**, so a 345px-wide card sits in the corner
of an 800px canvas with ~55% of the width and ~70% of the height empty. And 15px
text in a `quality: 40` JPEG is unreadable once QQ scales the image down for a
chat bubble.

For reference, AstrBot's own `base.html` t2i template uses `font-size: 25px` and
`main { width: min(100%, 920px) }` — the same shape we should have had.

## The fix

**`CARD_TEMPLATE` — fill the canvas, scale the type up**

```css
body  { font-size: 24px; padding: 22px 28px 28px; }
.card {
  width: max-content;                 /* wide tables stretch the card */
  min-width: 100%;                    /* short content still fills the width */
  min-height: calc(100vh - 50px);     /* fill the viewport height */
  display: flex; flex-direction: column;
  justify-content: safe center;       /* centre short content… */
}
```

Why those specific choices:

- `width: max-content` + `min-width: 100%` — a plain `min-width: 720px` would
  *not* fill a 1280px-wide viewport if the renderer ever used one, and a plain
  `width: 100%` would force a 13-column 肉质表 to wrap or overflow. Together they
  do both: the card is never narrower than the canvas, and grows when the table
  is wider than it.
- `min-height: calc(100vh - 50px)` — the leftover band at the bottom is the
  renderer's viewport floor, not our whitespace, so the card has to claim it.
- `justify-content: safe center` — `safe` makes the centring fall back to
  `flex-start` when the content is taller than the card, so a long table is never
  clipped at the top. (Verified: at a 300px-tall viewport the meat table renders
  from its title, not from the middle. And if a browser doesn't support the
  `safe` keyword the declaration is dropped entirely, which also leaves the
  content top-aligned — no clipping either way.)
- Heading sizes moved to `em`, table font to `.875em`, cell padding `7px 14px`.

**`CARD_RENDER_OPTIONS` — stop the JPEG mush**

```python
CARD_RENDER_OPTIONS: dict[str, object] = {"quality": 92}
```

AstrBot's default is `{"full_page": True, "type": "jpeg", "quality": 40}`, and
`Star.html_render(tmpl, data, return_url=True, options=…)` merges our dict *over*
those defaults — so only `quality` is overridden and nothing new is introduced
that a t2i endpoint might reject.

**Retry without options**

`_image_result` → `_render_card` now tries twice:

1. with `CARD_RENDER_OPTIONS`; if that raises `TypeError`, the host's
   `html_render` has no `options` parameter (older AstrBot) — fall through;
2. with plain defaults (no `options` argument).

Only if both fail does it degrade to plain text. Without this, passing `options`
at all would have silently cost `image` mode on older AstrBot versions.

## Verified visually

The two older screenshots are byte-for-byte the reported symptom; the new ones
are rendered through headless Chromium at the same 800×615 viewport the t2i
endpoint uses.

| | |
|---|---|
| before (`v0.3.2` template) | 345px card, top-left, ~15px text |
| after (`v0.3.3`) | full-width card, 24px text, vertically centred |
| after, 肉质表 | full-width card, table at 21px, right-aligned numbers |

Reproduce locally:

```powershell
python scripts/_card_preview.py     # writes the card HTML to %TEMP%
```

## Changes

- `core/render.py` — rebuilt `CARD_TEMPLATE`; new `CARD_RENDER_OPTIONS` exported
  via `__all__`.
- `main.py` — `_render_card()` with the two-attempt chain; `_image_result()`
  delegates to it; `PLUGIN_VERSION` → `0.3.3`.
- `metadata.yaml` — `version: 0.3.3`.
- README — the「图片为什么清晰、而且铺满整张？」note in the 输出格式 section.

## Tests

- `tests/test_render.py` (5 new cases) — the card is not shrink-wrapped (that
  assertion is made against the CSS with comments stripped, so the explanatory
  comment in the template can't mask a regression), it fills the canvas
  (`max-content` / `min-width: 100%` / `min-height`), the base font is ≥ 22px,
  vertical centring uses the `safe` keyword, and `CARD_RENDER_OPTIONS` raises
  `quality` above 40 while adding no other key.
- `tests/test_command_group.py` (3 new cases) — the high-quality options are
  actually passed through; a renderer whose signature rejects `options` still
  produces an image (the `TypeError` retry); a renderer that rejects the option
  *values* still produces an image (the defaults retry), asserting the attempt
  order is `[CARD_RENDER_OPTIONS, None]`.

Full suite: **136 cases** (was 128).

## Upgrade notes

- No data, command, or config changes.
- Reload the plugin (插件页 → 重载插件) and the next QQ query comes back as a
  full-width, readable card.
- Text-heavy queries are unaffected as always: errors and the 「⏳ 正在拉取…」
  line stay plain text.
