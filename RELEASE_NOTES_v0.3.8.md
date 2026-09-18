# astrbot_plugin_mhhelper v0.3.8

**BREAKING**: the `[作品]` suffix is gone from every command. There is one global
"current game" that an admin switches with `/mh 作品 <作品名>`.

## 1. `/mh 作品 <作品名>` — admin-only game switch

```
/mh 作品 荒野        (admin)
已切换到 怪物猎人:荒野。

之后所有查询都会使用该作品的数据。
（原先：怪物猎人:世界）
```

- The switch **writes back the plugin config's `default_game`** and saves it, so
  it survives a restart and shows up in the WebUI — the config option and the
  command stay in sync, as requested.
- Every query (怪物 / 技能 / 更新) uses that game; the per-user "last used game"
  memory is gone.
- `/mh 作品` without an argument still lists the enabled games, now marking the
  current one (`怪物猎人:荒野 — mhwilds（当前）`).
- Rejections: unknown game → `未知作品` + the valid ones; a disabled game →
  `作品不可用`; a non-admin → `需要管理员权限`. Nothing is changed in those cases.

## 2. `[作品]` removed from every command

`/mh 怪物 <名字>` and `/mh 技能 <名字>` no longer accept a trailing game token —
it is now simply part of the name (`/mh 怪物 雌火龙 mhrise` looks up
`雌火龙 mhrise` and misses). `/mh 更新` refreshes the current game.

If the configured game is disabled in the plugin settings, the plugin falls back
to the first enabled game instead of erroring (the `作品不可用` error is now only
reachable when nothing is enabled).

The per-user game persistence (`user_last_game.json` and the whole
state-directory resolution it needed) is gone — there is nothing left to store,
so `main.py` shrank by ~140 lines.

## 3. The switch is invisible to non-admins

The help text and the bare-`/mh` command tree only say `/mh 作品` — 列出已启用
的作品. The `<作品名>` variant exists purely as an argument to that same
sub-command, so there is no extra tree entry to hide, and the syntax is
documented here rather than in the bot's help. A non-admin who tries it gets
`需要管理员权限`.

(The runtime check is `event.is_admin()`; the `更新` command keeps its
decorator-based admin filter.)

## Changes

- `main.py` — global `_current_game()` / `_set_current_game()` (config-backed,
  `save_config()` guarded for test doubles), `_is_admin()`, merged `作品`
  handling, `[作品]` parsing removed, the state-file machinery deleted
  (~140 lines), `PLUGIN_VERSION` → `0.3.8`.
- `core/formatter.py` — `render_games(games, current=…)` marks the current game;
  new `render_switch_result()`; help text rewritten without `[作品]` and without
  the switching syntax.
- `_conf_schema.json` — `default_game` described as the current game.
- `README.md` — new「当前作品（全局）」section.

## Tests

- `tests/test_command_group.py` (+7 / −2) — the admin switch (message + config
  write-back + persistence across a plugin re-instantiation), the non-admin
  rejection, unknown/disabled targets, the current-game marker in `/mh 作品`,
  and that trailing game tokens are now part of the name.
- `tests/test_state_dir.py` deleted (13 cases) — the state file no longer exists.
- `tests/_astrbot_fake.py` — `_FakeEvent.is_admin()`, a `_FakeConfig` that
  records `save_config()` calls, and `make_plugin` re-running `_init_indexes()`
  after applying a config override (otherwise `_enabled_games` is stale).

Full suite: **184 cases** (was 197; −13 for the deleted state-file tests).

## Upgrade notes

- **Breaking**: a trailing `[作品]` no longer selects a game; use
  `/mh 作品 <作品名>` (admin).
- The previous per-user `user_last_game.json` files are simply ignored; nothing
  needs migrating.
- Reload the plugin (插件页 → 重载插件).
