# astrbot_plugin_mhhelper v0.3.7

Three fixes and one rule change.

## 1. Section headings shortened

| before | after |
|---|---|
| `### 属性弱点（最强两项）` | `### 属性弱点` |
| `### 状态异常累积值` | `### 异常累积` |

Only the visible headings changed — the "top two" rule itself is unchanged and
still documented in the code (`_WEAKNESS_TOP_N`), so the report is now:

```
锁刃龙
属性弱点
- 龙：38
- 火：30
肉质表
| 部位 | 状态 | … |
异常累积
| 毒 | 眠 | 麻 | 爆 | 晕 | 减气 |
| 150 | 150 | 180 | 70 | 120 | 225 |
```

## 2. Skill effects: 世界 was all `0`, 崛起 was English

Two separate bugs, both in `_parse_skill`:

**世界** — the detail page is *level | effect | parameter…* where the parameters
are `<code>` chips:

```html
<td>等级1</td><td><strong>减少受到中毒伤害的次数。</strong></td>
<td><code>200</code></td><td><code>0</code></td>…
```

The parser took `cells[-1]`, i.e. the last parameter column, so **every** world
skill's effect came out as `"0"` — which is exactly the `Lv 1 0 / Lv 2 0 / Lv 3 0`
in the report. The effect is always the **second** cell.

**崛起** — the detail page being scraped was `/data/skills/<id>` (English) instead
of `/zh/data/skills/<id>`. All 362 level effects were English.

Both are now parsed by one function, `parse_skill_levels()` in
`scraper/listing.py`, which takes the whole page, keeps the **first contiguous
run** of level rows (the tool/decoration tables further down have a non-level
first cell and are skipped), and reads the effect from cell 2. The world fetcher
also switched to `/zh/skilltrees/<id>/<slug>` — note the slug is required,
`/zh/skilltrees/<id>` alone is a 404 — with a fallback to the English page.

`data/skills/mhrise.json` and `data/skills/mhworld.json` were re-scraped, so the
effects are now Chinese for both.

A blank effect is legitimate on kiranico (e.g. 抑制偏移 Lv3 has no description),
and a level with no effect now renders as a bare `- **Lv 3**` instead of leaving
a trailing space.

## 3. Skill output is always text

`/mh 技能` no longer renders a card under **any** `output_mode`: a skill is a
heading plus a few bullets, which is shorter and more readable as text than as an
image. The handler now goes straight through `_text_result()`, so `image` /
`auto` / `markdown` / `text` all send the same plain text.

`/mh 怪物` is unaffected and still follows `output_mode`.

## Changes

- `core/formatter.py` — two headings renamed; `render_skill()` no longer appends a
  trailing space for a blank effect.
- `main.py` — `技能` bypasses `_emit()`; docstrings updated.
- `scraper/listing.py` — new `parse_skill_levels()` (pure regex, so the offline
  test suite and maintenance scripts can use it; `scraper/kiranico.py` imports
  bs4 at module level and would be unreachable without it). Its docstring now
  covers both listing pages and skill detail pages.
- `scraper/common.py` — both skill parsers call the shared function; the rise and
  world fetchers use the zh detail pages.
- `data/skills/mhrise.json`, `data/skills/mhworld.json` — re-scraped.
- `main.py` / `metadata.yaml` → `0.3.7`; README updated.

## Tests

- `tests/test_listing.py` (+5) — mhrise and mhworld level parsing, with a
  regression guard asserting the world effect is the second cell rather than one
  of the `<code>` parameters, that parsing stops at the first gap, that `Lv. 2`
  is accepted, and that a page with no level rows yields nothing.
- `tests/test_formatter.py` (+1) — a blank effect renders as `- **Lv 3**` with no
  trailing space.
- `tests/test_command_group.py` (+1) — `/mh 技能` returns plain text under all
  four `output_mode` values and never touches the renderer.
- Heading assertions updated for the new names.

Full suite: **197 cases** (was 190).

## Upgrade notes

- No config changes.
- Reload the plugin (插件页 → 重载插件). Skill effects then come back in Chinese,
  as text.
