# astrbot_plugin_mhhelper v0.2.0

Reworks command registration so the AstrBot admin panel shows **one** command
instead of twenty-one.

## Breaking change: `/mh <子命令>`

v0.1.x registered 21 flat top-level commands, so AstrBot's 「指令管理」 page was
cluttered with `/mh`, `/mh肉质`, `/mh_meat`, `/mh弱点`, `/mh_weak`, … — all
siblings, with no grouping.

v0.2.0 registers a single AstrBot **command group** (`@filter.command_group("mh")`)
and attaches every feature to it as a sub-command. The panel now shows one
collapsible `mh` row whose badge counts the sub-commands; expanding it lists the
second-level commands with their Chinese descriptions, and each one can be
enabled / disabled / renamed individually.

Consequently the command syntax gains a space:

| v0.1.x | v0.2.0 |
|---|---|
| `/mh肉质 火龙` | `/mh 肉质 火龙` |
| `/mh_meat Rathian` | `/mh meat Rathian` |
| `/mh怪物列表 mhrise` | `/mh 怪物列表 mhrise` |
| `/mh更新 mhwilds` | `/mh 更新 mhwilds` |

There is no longer a `/mh帮助` — the group alias `/怪物猎人` works
(`/怪物猎人 肉质 火龙`), and a bare `/mh` renders the auto-generated tree.

## Sub-commands

| 子命令 | Aliases | 说明 |
|---|---|---|
| `帮助` | `help` `用法` | 查看完整帮助 |
| `怪物列表` | `monsters` `怪物表` `list` | 列出该作品的全部大型怪物 |
| `怪物` | `monster` `info` | 怪物基础信息（种类 / HR 点数 / HP） |
| `肉质` | `meat` `肉` | 各部位肉质表 |
| `弱点` | `weak` `属性` | 属性弱点与状态异常累积值 |
| `素材` | `rewards` `报酬` `掉落` | 剥取 / 部位破坏 / 目标报酬 |
| `技能列表` | `skills` `技能表` | 列出该作品的全部技能 |
| `技能` | `skill` | 技能各等级效果 |
| `作品` | `games` `game` | 列出已启用的作品 |
| `更新` | `update` `刷新` | 管理员：在线刷新数据 |

Each handler's docstring is its panel description, so the description shown in
the admin UI and in the `/mh` tree cannot drift from the code.

## Other changes

- `/mh 更新` is now gated by `@filter.permission_type(ADMIN)` in addition to the
  existing `allow_runtime_update` config switch — previously any user could
  trigger a data refresh.
- Fixed `NameError: event is not defined` in the refresh handler; the refresh
  result was never delivered.
- Querying a game that is disabled via `enable_world` / `enable_rise` /
  `enable_wilds` now reports 「作品不可用」 instead of the misleading
  「未找到怪物」. The per-game enable flags are read once in `_init_indexes()`
  instead of being duplicated into both indexes.
- `render_help()` rewritten for the new syntax (includes game-identifier aliases
  and English sub-command aliases).
- More game aliases: `iceborne` → mhworld, `sunbreak` → mhrise.

## Tests

- `tests/_astrbot_fake.py` — a behaviour-faithful stand-in for the AstrBot API
  slice the plugin uses (command-group registration, `CommandFilter` matching,
  `CommandGroupFilter`, and the wake-prefix stripping done by
  `WakingCheckStage`), so registration can be tested without AstrBot installed.
- `tests/test_command_group.py` — 35 new cases that lock in the panel shape
  (exactly one root group, **no** bare top-level commands, the exact
  sub-command / alias table), the `/mh` tree, routing for every sub-command
  (including aliases and other wake prefixes), argument parsing, the admin gate
  and the per-user "last game" memory.
- `scripts/_import_test.py` — human-readable local smoke test that prints the
  command tree and a routing report (`python scripts/_import_test.py`). It is
  covered by `.gitignore`'s `scripts/_*.py` rule, so it stays untracked.

Full suite: 59 cases (24 pre-existing + 35 new).

## Upgrade notes

- Existing users must add the space: `/mh 肉质 火龙`.
- No data changes — `data/` payloads are identical to v0.1.0.
- Per-user "last game used" state (`plugin_data/user_last_game.json`) is
  unchanged.
