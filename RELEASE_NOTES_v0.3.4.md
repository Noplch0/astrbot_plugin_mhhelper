# astrbot_plugin_mhhelper v0.3.4

Follow-up to v0.3.3. The card fills the canvas now, but for **some monsters** the
outer margin was still uneven — the left gap was wider than the right one.

## Why only some monsters

The card is `width: max-content; min-width: 100%`, so a wide table stretches it
past the canvas width. The **body** stayed at its normal width though, so once
the card got wider than the body's padding box it simply overflowed to the right
and **ate the 28px right margin**. The left margin was untouched.

Measured at the t2i viewport (800px wide → 776px usable, 720px inside the body
padding):

| monster | table | card | left gap | right gap |
|---|---|---|---|---|
| 煌雷龙 | 650px | 720px (= usable width) | 28px | **28px** |
| 锁刃龙 | 710px | 780px (> usable width) | 28px | **0px** |

锁刃龙 has wider columns (`左锁翼刃` / `State_1` / `弱点`), which is why it was the
one that broke. Narrow tables were symmetric by accident: the card happened to be
exactly the usable width.

## The fix

```css
body {
  width: max-content;   /* grow with the card … */
  min-width: 100%;      /* … but never narrower than the canvas */
  padding: 22px 28px 28px;
}
```

With the body growing alongside the card, the right padding is preserved and the
document width becomes `28 + card + 28`, so `full_page` captures a symmetric
frame. The card itself does not move at all — verified with the same element
rectangles before and after (`card x 28 .. 808` in both cases); what changed is
the document width, **808 → 836**, which is exactly the missing right margin.

| | document | outer gaps |
|---|---|---|
| before | 808px | 28 / **0** |
| after | 836px | 28 / **28** |

## Verified

Headless Chromium, viewport sized to the document, measuring `getBoundingClientRect`
and cross-checking the produced PNG pixels:

```
=== v0.3.3  锁刃龙   (window 838x1364, document 836x1362)
    card  x 28 .. 808
    table x 63 .. 773
    OUTER gaps  left 28  right 28   -> ASYMMETRY 0
    inner inset left 35  right 35
```

A note on method, since it cost me a wrong turn: my first screenshot harness
injected its measurement `<pre>` into the very page it then screenshotted, and the
long unbroken JSON line inflated the document's max-content — producing a wide,
"impossible" layout that contradicted the DOM numbers. Screenshots are now taken
from a pristine copy of the page.

## Changes

- `core/render.py` — `body` gains `width: max-content; min-width: 100%`
  (replacing `min-width: 320px`, which is subsumed). `CARD_TEMPLATE` only.
- `main.py` / `metadata.yaml` — `0.3.4`.
- README — the 图片为什么清晰 note now explains the body-grow requirement.

## Tests

- `tests/test_render.py` (+1, now 6 card-layout cases) — a regression guard
  asserting that **both** `body` and `.card` carry `width: max-content` and
  `min-width: 100%`. A new `_rule()` helper extracts a selector's declaration
  block from the comment-stripped CSS, so the assertion is about the rule that
  matters rather than a substring somewhere in the file.

Full suite: **137 cases** (was 136).

## Upgrade notes

- No data, command, or config changes.
- Reload the plugin (插件页 → 重载插件); the next QQ query comes back with even
  margins on both sides.
