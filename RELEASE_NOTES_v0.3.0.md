# astrbot_plugin_mhhelper v0.3.0

Query results are no longer shipped as whitespace-aligned plain text. The
formatter now emits **markdown**, and a new `output_mode` config decides how
that markdown reaches the user — including rendering it to an **image card**
for QQ, which cannot render markdown at all.

## Why not just send markdown?

| 平台 | 会渲染 markdown 吗 |
|---|---|
| QQ 个人号（NapCat / aiocqhttp） | ❌ 只支持 文字 / 图片 / 语音 |
| QQ 官方机器人 | 平台侧支持自定义 markdown，但 AstrBot 适配器对外只暴露 文字 / 图片 |
| Telegram / 飞书 / Discord / Slack | ✅ 原生渲染 |

On QQ 个人号, sending `| 部位 | 斩 | … |` as text makes things **worse** — the
chat box shows the raw pipes and dashes. (And the `+---+` borders from v0.1.0
were worse still; v0.2.0 replaced those with space alignment, which still
shears apart on a phone.) The only way to keep a wide table readable on QQ is
to render it into a picture, so that is what `output_mode="image"` does.

## New config: `output_mode`

| `output_mode` | 行为 |
|---|---|
| `auto` (default) | QQ 全系 → `image`；Telegram / 飞书 / Discord / Slack / WebChat → `markdown`；其他 → `text` |
| `image` | AstrBot 文转图（`Star.html_render`）渲染成图片卡片 |
| `markdown` | 直接发 markdown 原文 |
| `text` | 退化成空格对齐的纯文本 |

`auto` uses `event.get_platform_name()`; anything unrecognised falls back to
`text`, so a brand-new adapter can never produce something unreadable.

## Graceful degradation

`image` never becomes a failure mode. If the host has no working 文转图
(missing Playwright, renderer unreachable, …) the plugin logs a warning and
delivers the plain-text rendering instead. Error messages and the
「⏳ 正在拉取…」 progress line always go out as plain text — they never trigger a
render.

## Changes

**New `core/render.py`**

- `resolve_mode(mode, platform)` — the `auto` policy above.
- `markdown_to_plaintext(md)` — markdown → aligned plain text. Reuses the
  CJK-aware column alignment, so the `text` fallback is at least as readable as
  v0.2.0's output.
- `markdown_to_html(md)` — markdown → HTML fragment, for the card.
- `CARD_TEMPLATE` — the HTML/CSS card (white rounded card, dark table header,
  zebra striping, tabular numerals, inline-code chips).

Both converters understand only the deliberately small markdown subset that
`core/formatter.py` emits (headings, `-` bullets, GFM pipe tables, `**bold**`,
`` `code` ``, `---`), so no markdown library is needed and both are unit-testable
offline.

**`core/formatter.py` — now markdown-first**

Every `render_*` returns markdown instead of plain text:

```
### 🍖 雌火龙 — 肉质表

| 部位 | 状态 | 斩 | 打 | 弹 | 火 | 水 | 雷 | 冰 | 龙 | 麻 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 头部 | 通常 | 70 | 75 | 65 | 0 | 15 | 20 | 15 | 30 | 100 |
```

- `md_table()` builds the pipe table; `light_table()` is retained for the
  plain-text path.
- Columns whose header looks numeric — now including the 斩 / 打 / 弹 / 火水雷冰龙
  meat columns — are right-aligned (`---:`), so values line up when scanned
  vertically.
- Cell content containing `|` is escaped (`\|`), so a reward named `a|b` cannot
  break the table.

**`main.py`**

- New `_emit(event, markdown)` → `_text_result()` / `_image_result()` delivery
  chain. Every content path now goes through `_emit`; errors and the refresh
  progress line go through the plain-text path.
- `_platform_name(event)` reads `get_platform_name()` / `get_platform_id()`,
  falling back to the first segment of `unified_msg_origin`.

## Tests

- `tests/test_render.py` (new, 28 cases) — mode resolution for every documented
  platform plus unknown/empty/bogus input; markdown → plain text (markers
  stripped, table rebuilt and width-aligned, escaped pipes survive); markdown →
  HTML (table structure and per-column alignment, headings, bullets, bold,
  inline code, HTML escaping, escaped pipes).
- `tests/test_formatter.py` — extended with markdown-contract cases (GFM
  separator row, right-aligned numeric columns, bullets).
- `tests/test_command_group.py` — 7 new cases covering every `output_mode`,
  including the `image` → plain-text fallback when the renderer is missing or
  raises, and that errors bypass rendering entirely.
- `tests/_astrbot_fake.py` — `_FakeEvent` gained `get_platform_name()` /
  `unified_msg_origin` / `image_result()`, and `dispatch()` accepts `platform=`.

Full suite: **97 cases** (was 59).

## Upgrade notes

- No data changes — `data/` payloads are identical to v0.2.0.
- No command changes — `/mh <子命令>` syntax is unchanged.
- The default `auto` mode changes what a QQ user sees: results arrive as image
  cards. Set `output_mode = "text"` to get the old space-aligned plain text
  back, or `"markdown"` to send markdown.
- `image` mode depends on AstrBot's built-in 文转图. Without it the plugin
  degrades to plain text automatically.
