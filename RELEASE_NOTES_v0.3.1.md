# astrbot_plugin_mhhelper v0.3.1

A bug-fix release. Two things: a load-time import error that could take the
whole plugin down, and the runtime state directory, which now follows
AstrBot's official storage spec.

## Fixed: `cannot import name 'light_table' from 'core.formatter'`

Reported as a plugin load failure at
`/AstrBot/data/plugins/astrbot_plugin_mhhelper/core/formatter.py`.

`light_table()` was renamed from `_light_table()` in v0.3.0, and the new
`core/render.py` imports it by its public name. That is fine on a consistent
install — **both changes landed in the same commit**, so v0.2.0 and v0.3.0 are
each internally coherent. The failure only happens in a *mixed* install: an old
`formatter.py` (v0.2.0, which only defines `_light_table`) sitting next to a new
`render.py`. In that state `render.py`'s import raises at module load and the
plugin never starts.

`core/render.py` now resolves both names:

```python
try:
    from .formatter import light_table
except ImportError:  # legacy formatter (< v0.3.0)
    from .formatter import _light_table as light_table
```

Both spellings have the same signature, so a mixed install now loads and
degrades gracefully instead of failing outright.

> If you hit this, the real fix is still to let AstrBot replace the plugin
> directory wholesale — click **重载插件** on the plugin card, or uninstall and
> reinstall. This release makes the failure non-fatal so that a partial update
> can never brick the plugin again.

## Changed: runtime state moved to AstrBot's `data/`

AstrBot's plugin dev guide is explicit:

> 持久化数据请存储于 `data` 目录下，而非插件自身目录，防止更新/重装插件时数据被覆盖。

v0.3.0 and earlier wrote the per-user "last game used" map into
`plugin_data/user_last_game.json` **inside the plugin directory**, which
AstrBot replaces on every update. v0.3.1 writes it to the documented location
instead:

```
<AstrBot>/data/plugin_data/astrbot_plugin_mhhelper/user_last_game.json
```

resolved via the official API:

```python
from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
```

Resolution degrades in three steps so the plugin still starts on any AstrBot
version or directory layout:

| # | Resolution | When it applies |
|---|---|---|
| 1 | `get_astrbot_data_path() / "plugin_data" / <name>` | official API available (normal) |
| 2 | infer from the install path: plugin at `<root>/data/plugins/<name>` → `<root>/data/plugin_data/<name>` | older AstrBot without that API |
| 3 | fall back to `plugin_data/` inside the plugin directory (with a WARNING) | neither works — only to avoid a hard failure |

### Migration

Upgrading from v0.3.0 needs no user action. The old plugin-local
`plugin_data/user_last_game.json` is *read* on startup (so nobody loses their
last-used game), written to the new location on save, and only then deleted —
along with the now-empty directory. A directory that still holds other files is
left alone. If the write fails, the legacy file is kept.

## Changes

- `core/render.py` — dual-name import for `light_table`; `light_table` added to
  `__all__`.
- `main.py` — `_official_state_dir()` / `_derived_state_dir()` /
  `_legacy_state_path()` / `_plugin_state_dir()` resolution chain;
  `_load_user_state()` reads new-then-legacy and tolerates a corrupt file;
  `_save_user_state()` cleans up the legacy copy after a successful write;
  `STATE_FILENAME` / `LEGACY_STATE_DIRNAME` constants; `PLUGIN_VERSION` → `0.3.1`.
- `metadata.yaml` — `version: 0.3.1`.
- `.gitignore` — comment updated; `plugin_data/` stays ignored, since the
  fallback (and an upgrade from v0.3.0) can still leave one behind.

## Tests

- `tests/test_state_dir.py` (new, 17 cases) — official API wins over path
  sniffing, every step of the degradation chain, an unwritable official
  directory falls through, constants match the documented layout, a source-level
  guard that the official API import is still there, and the full legacy
  migration (read → write → cleanup, corrupt/non-dict payloads, values coerced
  to strings, a shared directory left intact, fallback mode not deleting its
  own file).
- `tests/test_render.py` — 3 new cases: `light_table` is re-exported, the
  plain-text table path still works, and the legacy import fallback is present.
- `tests/_astrbot_fake.py` — `make_plugin()` redirects the state directory only
  for the duration of `__init__` and then restores the class attribute. It
  previously patched the class permanently, which leaked the redirect into
  every later test *and test module* (the loaded module object is cached).

Full suite: **117 cases** (was 97).

## Upgrade notes

- No data changes — `data/` payloads are identical to v0.3.0.
- No command changes — `/mh <子命令>` syntax is unchanged.
- No config changes — `output_mode` and the rest are untouched.
- If you run a very old AstrBot without `astrbot.core.utils.astrbot_path`, the
  plugin derives the data directory from its own install path. Check the logs
  for a WARNING if state ever lands in the plugin directory.
