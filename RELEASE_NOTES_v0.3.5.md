# astrbot_plugin_mhhelper v0.3.5

Three changes: a wrong line in `弱点`, shorter status-ailment labels, and the
monster's in-game icon on the image card.

## 1. `弱点` showed 晕厥 as an elemental weakness

`属性弱点概览` listed a `麻：100` row. kiranico's meat table does label that last
column `麻`, but the value is actually **晕厥 (stun)** — the same report already
lists 麻痹 separately under 状态异常累积值. The row is gone:

```
### 属性弱点概览（各部位最大值）
- **火**：5
- **水**：20
- **雷**：0
- **冰**：25
- **龙**：5          ← 不再有「麻」
```

The element list is now `_ELEMENT_COLUMNS = {"火","水","雷","冰","龙"}`, so the
column cannot come back by accident.

## 2. Shorter status-ailment labels

`状态异常累积值` now uses one character per row, as requested:

| before | 毒 | 睡眠 | 麻痹 | 爆破异常 | 昏厥 | 减气 |
|---|---|---|---|---|---|---|
| after | 毒 | **眠** | **麻** | **爆** | **晕** | 减气 |

`减气` is unchanged, and an unmapped key is passed through verbatim rather than
dropped. MHWorld's page also carries English rows, so `Mount` / `Captures` /
`Stamina` are labelled 骑乘 / 捕获 / 减气 instead of leaking English into a
Chinese list.

## 3. The monster icon on the image card

`image` mode now puts the monster's in-game portrait at the top of the card, with
the monster name centred underneath it. **Nothing else changed** — `text` and
`markdown` output are byte-for-byte what they were, and non-monster queries
(作品 / 帮助 / 列表) simply have no icon.

```
        ┌──────────┐
        │  [icon]  │        ← 居中
        └──────────┘
        🍖 锁刃龙 — 肉质表   ← 居中
| 部位 | 状态 | 斩 | 打 | …  ← 其余不变
```

### Where the icons come from, and why the old field was useless

The data already had an `icon` field, but it was a placeholder: **every one of
the 55 mhwilds monsters pointed at `EM0001.webp`**, and that URL 404s (the real
one is `EM0001_00_0.webp`). `scraper/common.py` even said so:

```python
def _icon_id(self, slug: str) -> str:
    # placeholder: real icon ids require a separate lookup; we leave 0001
    return "0001"
```

Icons only exist on the **listing** pages, and the three sites share nothing:

| game | url | markup | id in `data/` |
|---|---|---|---|
| 荒野 | `mhwilds.kiranico.com/zh/data/monsters` | `em_icon/EM0001_00_0.webp` | pinyin slug |
| 崛起 | `mhrise.kiranico.com/zh/data/monsters?view=lg` | `cdn…/mhrise-web/images/icons/em132_05.png` | numeric id |
| 世界 | `mhworld.kiranico.com/zh/monsters` | `cdn…/mhworld-web/mhw/icon/em105_ID.png` | 5-char code |

New `scraper/icons.py` isolates all of that in three pure-`re` functions
(`parse_mhwilds_icons` / `parse_mhrise_icons` / `parse_mhworld_icons`). They are
used by both the scrapers and the offline tests, so there is exactly one
definition of "how to find an icon" per site.

Pairing needs no magic offsets: each icon opens a window that ends where the next
icon starts, and the first monster link inside that window is its monster. Rows
are icon-per-monster on all three sites, so this cannot drift across rows — an
earlier version used a fixed 900-character window and silently missed 24 MHWorld
monsters.

Deliberate exclusions, each with a test: `element_N.png` (elemental weakness
chips) and `ib_icon.png` (Iceborne badge) on the world page, cover art on rises,
and the language-switcher links (`/data/monsters?view=lg`) which look like
monster links but carry no id.

Results, all 100%:

```
mhwilds  55/55      mhrise  78/78      mhworld  95/95
```

All URLs are https — mhrise serves its icons over `http://`, which an
https-rendered card would reject as mixed content. Every URL was spot-checked
with a real fetch (200, 256–512px sources).

### Rendering

`CARD_TEMPLATE` gained a `{{ hero | safe }}` slot plus:

```css
.hero      { display: flex; justify-content: center; }
.hero:empty { display: none; }        /* 没有图标就彻底不占位 */
.hero img  { width: 120px; height: 120px; object-fit: contain; }
.body > :first-child { text-align: center; }   /* 怪物名居中 */
```

`core/render.py` gained `monster_icon()` (guards against a missing or non-http
value) and `card_hero()` (emits the `<img>`, with `onerror="this.remove()"` so a
failed load degrades to "just the centred name" instead of a broken-image icon).
`main.py` threads the monster through `_emit(..., monster)` → `_image_result` →
`_render_card`, and the template data is now `{"content": …, "hero": …}`.

The icon URL is committed with the data, so **querying still needs no network**;
it is the t2i endpoint that fetches the image when rendering.

### Also: the dead `with_icon` config is gone

`_conf_schema.json` advertised `with_icon` («是否在结果附带怪物图鉴图标») but no
code ever read it. Now that the icon is automatic in `image` mode, keeping a
switch that does nothing would be actively misleading, so it was removed from the
schema, the defaults and the README.

## Scraper changes

`/mh 更新` rewrites `data/monsters/*.json` from scratch, so the scrapers had to
learn about icons or a refresh would wipe them:

- each scraper gained `GAME` and attaches `icon` to every item from
  `list_monsters()` (icons live on the listing page, which that method already
  fetches);
- `_parse_monster()` now returns `"icon": ""` instead of the fake
  `EM{0001}.webp`, and the `_icon_id` placeholder is deleted;
- `run_update._fetch_mon` copies `item["icon"]` onto the monster.

`data/monsters/*.json` was regenerated in place: the diff is **only** the `icon`
lines (55 + 78 + 95).

## Tests

- `tests/test_icons.py` (new, 16 cases) — per-site mapping, the http→https
  upgrade, the row-scoped pairing (including "a row with no link must not steal
  the next row's"), every deliberate exclusion, dispatch, and that the three
  index URLs are the documented pages.
- `tests/test_formatter.py` (+8) — single-char labels in order, 减气 unchanged,
  unmapped keys passed through, MHWorld's English keys labelled, the 麻 row gone
  from 属性弱点概览 (and its value 100 no longer present), max-across-parts, and
  the name heading still first.
- `tests/test_render.py` (+9) — the hero slot, `.hero:empty`, the centred first
  line, a sane icon size, and `monster_icon` / `card_hero` rejecting missing,
  non-http and bogus values while escaping the URL they emit.
- `tests/test_command_group.py` (+4) — the icon really reaches the card in image
  mode, no hero for an icon-less monster or a non-monster query, and `text` /
  `markdown` output contains neither the icon nor an `<img>` (and never renders).
- `tests/fixtures/monsters_sample.json` — 雌火龙 carries an icon, 神龙 does not,
  so both branches are covered.

Full suite: **173 cases** (was 137).

## Upgrade notes

- No command or config changes that affect existing setups (removing a dead key).
- Reload the plugin (插件页 → 重载插件) and the next QQ query comes back with the
  monster's portrait.
- If the t2i endpoint cannot reach kiranico, the card simply has no portrait; a
  warning is not logged for that case, and nothing else changes.
