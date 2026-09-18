# astrbot_plugin_mhhelper v0.3.6

Reshapes the command surface and the output layout, drops the heading emoji, and
fixes the reason 崛起/世界 showed internal ids instead of names.

## 1. One `/mh 怪物` instead of three commands

`怪物`（基础信息） / `肉质` / `弱点` are merged into a single command. The report
always has the same four parts, in this order — **in both text and image mode**:

```
      [怪物图标]            ← 仅图片模式，居中
       锁刃龙               ← 居中

属性弱点（最强两项）
- 龙：38
- 火：30

肉质表
| 部位 | 状态 | 斩 | 打 | … |     ← 与以前完全一样

状态异常累积值
| 毒 | 眠 | 麻 | 爆 | 晕 | 减气 |   ← 横向表格：种类在上、数值在下
| 150 | 150 | 180 | 70 | 120 | 225 |
```

- **属性弱点只留最强的两项**，并带上数值（用户给的例子：煌雷龙 → `冰 25` / `水 20`）。
  各属性为 0 的不算弱点；全 0 时输出「无属性弱点」。同数值按 火水雷冰龙 稳定排序。
- **状态异常横过来排**成两行表格，取代原来的一列清单。为了这几个列头也能右对齐，
  `_NUMERIC_HINTS` 补上了 `晕 / 减气 / 骑乘 / 捕获 / 龙封`（`爆` 也补了 ——
  标签压成单字后，原来的 `爆破` 提示匹配不到 `爆`）。
- `肉质` / `弱点` / `属性` / `meat` / `weak` **保留为别名**，返回同一份合并报告，
  习惯输入照旧可用。不需要的话说一声就删。

## 2. Deleted: 怪物列表 / 技能列表 / 素材

The three sub-commands are gone, along with their renderers
(`render_monster_list`, `render_skill_list`, `render_rewards`,
`render_monster_info`, and the old `render_meat` / `render_weak`). The `mh` group
is now five entries: 帮助 / 怪物 / 技能 / 作品 / 更新.

## 3. No more heading emoji

`### 🍖 锁刃龙 — 肉质表` → `## 锁刃龙`. Every heading lost its emoji, and the
report title is just the monster name so the card can centre it under the icon.
(`⚠️` / `✅` on error and update messages are status markers rather than name
decorations, so they stay — say the word if you want those gone too.)

## 4. Fixed: 崛起/世界 showed internal ids as names

The screenshots showed `1301934382 (Primordial Malzeno)` and
`KpViL (Acidic Glavenus)`. Cause: `name_zh` was **empty for every mhrise/mhworld
entry** (78 + 95 monsters and 147 + 203 skills), so the name helper fell through
to `id`.

Two fixes:

- `_display_name()` now resolves **中文名 → 英文名 → id**, so an id can never
  leak into the UI again — worst case you get the English name, which is readable.
- The Chinese names are now **filled in from kiranico's zh listing pages**:
  78 + 95 monsters and 147 + 203 skills. The README's old claim that those two
  games are English-only was simply wrong: the zh index pages have full Chinese
  names (`伞鸟`, `硫斩龙`, `攻击`, `毒耐性`, …). The report title is now e.g.
  `## 硫斩龙 (Acidic Glavenus)`.

## 5. `scraper/icons.py` → `scraper/listing.py`

The same listing pages carry both the icon and the Chinese name, so the module
now parses both from the same row instead of duplicating row-matching rules:

| page | id | icon | 中文名 |
|---|---|---|---|
| mhwilds monsters | pinyin slug | `em_icon/EM0001_00_0.webp` | anchor text (inside a `<span>`) |
| mhrise monsters | numeric | `images/icons/em132_05.png` | `img alt` |
| mhworld monsters | 5-char code | `icon/em105_ID.png` | anchor text |
| mhrise skills | numeric | — | nested anchor text |
| mhworld skills | 5-char code | — | anchor text |

Coverage against the live pages is **100% on all five** (55 / 78 / 95 monsters,
147 / 203 skills). Names are stripped of inner tags, so the mhwilds `<span>` and
the mhrise skill `<p>` nesting come out clean.

The scrapers now fetch the **zh** index pages (details still come from the
English pages, which have the meat/ailment tables) and pass both fields down, so
`/mh 更新` no longer wipes them.

## 6. Kept as-is

You said the `?` cells in the meat table are fine to leave — they are. That
column is empty in kiranico's own wilds table for some rows (15 of 55 monsters,
75 rows), and the renderer keeps filling unavailable cells with `?`.

## Changes

- `core/formatter.py` — `render_monster_report()` + `_display_name()` /
  `_element_weakness()` / `_weakness_section()` / `_ailments_section()` /
  `_meat_section()`; six old renderers deleted; heading emoji removed;
  `_NUMERIC_HINTS` completed.
- `core/render.py` — unchanged (the card's hero slot and centred first line are
  what centre the icon + name).
- `main.py` — merged dispatch branch, five-entry command group, new USAGE table,
  `_GAME_ONLY_SUBS` trimmed, `PLUGIN_VERSION` → `0.3.6`.
- `scraper/listing.py` (renamed from `icons.py`), `scraper/common.py`,
  `scraper/run_update.py` — zh index pages, name propagation.
- `data/monsters/*.json`, `data/skills/*.json` — `name_zh` filled for
  mhrise/mhworld.
- `metadata.yaml`, README, `scripts/_card_preview.py`.

## Tests

- `tests/test_listing.py` (renamed, 22 cases) — all five pages, the http→https
  upgrade, row-scoped pairing, tag-stripping, every deliberate exclusion, and the
  zh index URLs.
- `tests/test_formatter.py` (rewritten) — section order, the top-two weakness
  rule (including the user's 煌雷龙 example), the transposed ailment table and its
  right-aligned columns, no-emoji headings, `_display_name` fallbacks, and that
  an id never reaches the output.
- `tests/test_command_group.py` — five-entry group, merged routing, alias
  compatibility (`/mh 肉质` … still works), and that the three deleted
  sub-commands now match nothing.

Full suite: **190 cases** (was 173).

## Upgrade notes

- **Breaking**: 怪物列表 / 技能列表 / 素材 no longer exist, and `/mh 怪物` now
  returns a four-part report instead of just the basic info.
- Existing configs are unchanged.
- Reload the plugin (插件页 → 重载插件).
