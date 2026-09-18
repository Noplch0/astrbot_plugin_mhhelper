# astrbot_plugin_mhhelper v0.3.2

**Root cause found** for the load failures that v0.3.1 only papered over. The
plugin was importing its own subpackages under names AstrBot never cleans up, so
after an update the process kept serving the *previous* version's code — which is
why the error message pointed at a file that visibly contained the missing name.

## The symptom

```
cannot import name 'light_table' from 'core.formatter'
(/AstrBot/data/plugins/astrbot_plugin_mhhelper/core/formatter.py)
```

…while the `formatter.py` at exactly that path *does* define `light_table`. After
v0.3.1 shipped a name-compatibility shim, the same install failed again, now with
`cannot import name '_light_table' from 'core.formatter'` — i.e. **neither** name
was visible, even though no released version of this plugin has ever lacked both.
That is what finally gave the game away: the module object in memory was not
describing the file on disk.

## Root cause

AstrBot imports a plugin as `data.plugins.<plugin dir>.main` and, when reloading
or updating it, purges `sys.modules` entries whose name starts with
`data.plugins.<plugin dir>` — `PluginManager._purge_modules` in
`astrbot/core/star/star_manager.py`, fed by the `path = "data.plugins." +
root_dir_name + "." + module_str` construction in `load()`.

This plugin's own subpackages are imported by their **bare top-level** names:
`core.data_loader`, `core.formatter`, `core.render`, `scraper.common`. That
prefix never matches those, so they **survive a plugin reload**. The freshly
loaded `main.py` then binds the stale module objects, and every import error it
reports describes code that is no longer on disk.

Two consequences, both real:

1. updates appear to do nothing, or fail with impossible import errors;
2. `core` is a generic enough top-level name that another plugin can claim it
   first, in which case this plugin would silently import somebody else's code.

## The fix

`main.py` now evicts the affected `sys.modules` entries **before** importing
anything, and keeps a fixed list of the plugin's own top-level packages:

```python
_INTERNAL_PACKAGES: tuple[str, ...] = ("core", "scraper")
```

The rule is deliberately **name-based**, not path-based: the plugin directory also
contains `tests/`, and a path rule would evict those too. Being name-based also
makes the same code handle the squatter case — the name is dropped whether the
entry is ours from a previous version or another plugin's, with a WARNING logged
in the latter case.

```python
_EVICTED_MODULES: list[str] = _evict_stale_modules()
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))
```

`main.py` is always re-executed on reload — AstrBot does purge its own module —
so the eviction runs exactly when it is needed. The log line:

```
[astrbot_plugin_mhhelper] dropped 4 stale module(s) left over from a previous
load: core, core.data_loader, core.errors, core.formatter
```

## Why this is worth a release on its own

It explains both earlier reports. The v0.3.0 bug report and the v0.3.1 one were
the *same* defect seen twice, and the v0.3.1 work (tolerating a missing
`light_table`) could only ever hide the symptom, because the real problem was
which module object got bound, not what names it exposed.

The v0.3.1 dual-name fallback in `core/render.py` **stays** — it costs nothing
and still covers a genuinely stale `formatter.py` on disk.

## Verified by reproduction

A throwaway subprocess loads a real v0.2.0 `core` package into `sys.modules`
(the stale generation), then:

```
PASS  loaded a stale (v0.2.0) core.formatter into sys.modules
PASS  reproducing the reported failure: cannot import name 'light_table' from
      'core.formatter' (...\wb_stale_v020_...\core\formatter.py)
PASS  main.py loaded with stale modules still in sys.modules
      evicted at import: ['core', 'core.data_loader', 'core.errors', 'core.formatter']
PASS  core.formatter rebound to the on-disk file: ...\core\formatter.py
PASS  render.py works against the fresh formatter
PASS  plugin instance constructed
```

Step 2 asserts the exact reported `ImportError` is reproducible *before* the fix
runs, so this is a reproduction, not just a green check.

## Changes

- `main.py` — import bootstrap (`_stale_module_names()`, `_evict_stale_modules()`,
  `_module_origin()`, `_is_inside_plugin_dir()`, `_INTERNAL_PACKAGES`); the
  `sys.path` insert now happens after the eviction; `PLUGIN_VERSION` → `0.3.2`.
- `tests/test_import_bootstrap.py` (new, 11 cases).
- `metadata.yaml` — `version: 0.3.2`.
- README — new「更新插件后为什么还在跑旧代码」section; the upgrade note replaced
  by one that reflects the actual mechanism.

## Tests

`tests/test_import_bootstrap.py` covers:

- the eviction rule evicts `core`, `core.*`, `scraper`, `scraper.*`, and keeps
  `json`, `tests`, `tests.*`, `astrbot_plugin_mhhelper.main`,
  `data.plugins.astrbot_plugin_mhhelper.main`, and near-misses like `coreutils`
  / `mycore` / `scraper_helpers`;
- `None` placeholders (a module mid-import) are left alone;
- the rule is name-based, demonstrated against `tests/__init__.py`, which lives
  inside the plugin directory;
- `_evict_stale_modules()` really pops, restoring the real modules afterwards;
- whatever `core` resolved to is a file inside this plugin's directory;
- **`_INTERNAL_PACKAGES` is complete**: `main.py` is parsed and every first-party
  root it imports by a bare top-level name (indented imports included, so the
  lazy `from scraper…` inside `_update` counts) must be registered. Adding a new
  subpackage without registering it fails the suite;
- the eviction and the `sys.path` insert both happen before `from core… import`.

Full suite: **128 cases** (was 117).

## Upgrade notes

- No data, command, or config changes.
- **No AstrBot restart required.** Reload the plugin once (插件页 → 重载插件); the
  bootstrap drops the stale modules and re-imports from disk.
- If you ever see `dropped N stale module(s)` in the log, that was the old code
  being cleared — expected, once per update.
- `_INTERNAL_PACKAGES` must list every top-level package `main.py` imports by a
  bare name. The test suite enforces it.
