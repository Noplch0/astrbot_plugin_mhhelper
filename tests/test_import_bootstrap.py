"""The import bootstrap that makes plugin updates actually take effect.

AstrBot imports a plugin as ``data.plugins.<dir>.main`` and, on reload/update,
purges ``sys.modules`` entries whose name starts with ``data.plugins.<dir>``
(``PluginManager._purge_modules`` in ``astrbot/core/star/star_manager.py``).

Our subpackages are imported by their bare top-level names — ``core.formatter``,
``scraper.common`` — which that prefix never matches. So before this fix, a
plugin update left the *previous* version's submodules alive in memory, and the
fresh ``main.py`` bound them: the resulting ``ImportError`` wouldn't match the
files on disk at all. That is precisely how a correctly-shipped release can fail
to load with

    cannot import name 'light_table' from 'core.formatter'

even though the deployed ``core/formatter.py`` does define it.

These tests pin the eviction rule and, importantly, keep
``_INTERNAL_PACKAGES`` in sync with what ``main.py`` actually imports.
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path

from tests import _astrbot_fake

REPO_ROOT = Path(__file__).resolve().parent.parent


def _mod():
    return _astrbot_fake.load_plugin()


def _fake_module(name: str, file: str | None) -> types.ModuleType:
    module = types.ModuleType(name)
    if file is not None:
        module.__file__ = file
    return module


# --------------------------------------------------------------------------
# _stale_module_names — the pure decision rule
# --------------------------------------------------------------------------


def test_our_own_submodules_are_stale():
    mod = _mod()
    modules = {
        "core": _fake_module("core", None),
        "core.formatter": _fake_module("core.formatter", None),
        "core.render": _fake_module("core.render", None),
        "scraper": _fake_module("scraper", None),
        "scraper.common": _fake_module("scraper.common", None),
    }
    assert sorted(mod._stale_module_names(modules)) == sorted(modules)


def test_unrelated_modules_are_kept():
    mod = _mod()
    modules = {
        "json": _fake_module("json", "/usr/lib/python3/json/__init__.py"),
        "tests": _fake_module("tests", None),
        "tests._astrbot_fake": _fake_module("tests._astrbot_fake", None),
        "astrbot_plugin_mhhelper.main": _fake_module("astrbot_plugin_mhhelper.main", None),
        "data.plugins.astrbot_plugin_mhhelper.main": _fake_module(
            "data.plugins.astrbot_plugin_mhhelper.main", None
        ),
        # 名字只是以 core/scraper 开头，并不是我们的包
        "coreutils": _fake_module("coreutils", None),
        "scraper_helpers": _fake_module("scraper_helpers", None),
        "mycore": _fake_module("mycore", None),
    }
    assert mod._stale_module_names(modules) == []


def test_none_entries_are_ignored():
    """A ``None`` placeholder means "being imported" — leave it alone."""
    mod = _mod()
    assert mod._stale_module_names({"core": None}) == []


def test_rule_is_name_based_not_path_based():
    """``tests/`` lives in the plugin dir too, so a path rule would be wrong."""
    mod = _mod()
    modules = {"tests": _fake_module("tests", str(REPO_ROOT / "tests" / "__init__.py"))}
    assert mod._stale_module_names(modules) == []


# --------------------------------------------------------------------------
# eviction + origin helpers
# --------------------------------------------------------------------------


def test_module_origin_handles_missing_file_attribute():
    mod = _mod()
    assert mod._module_origin(_fake_module("x", None)) is None
    assert mod._module_origin(_fake_module("y", str(REPO_ROOT / "main.py"))) == (
        REPO_ROOT / "main.py"
    ).resolve()


def test_is_inside_plugin_dir():
    mod = _mod()
    assert mod._is_inside_plugin_dir(REPO_ROOT)
    assert mod._is_inside_plugin_dir(REPO_ROOT / "core" / "formatter.py")
    assert not mod._is_inside_plugin_dir(REPO_ROOT.parent / "somewhere_else.py")


def test_evict_stale_modules_really_pops_and_restores_cleanly():
    """Seed a squatter, evict it, and make sure the real modules come back."""
    mod = _mod()
    roots = mod._INTERNAL_PACKAGES
    affected = [n for n in list(sys.modules) if n.split(".", 1)[0] in roots]
    snapshot = {n: sys.modules[n] for n in affected}
    for name in affected:
        sys.modules.pop(name)
    try:
        squatter = _fake_module("core", "/opt/other_plugin/core/__init__.py")
        sys.modules["core"] = squatter

        evicted = mod._evict_stale_modules()

        assert "core" in evicted
        assert "core" not in sys.modules
        assert not [n for n in sys.modules if n.split(".", 1)[0] in roots]
    finally:
        for name in [n for n in list(sys.modules) if n.split(".", 1)[0] in roots]:
            sys.modules.pop(name)
        sys.modules.update(snapshot)


def test_real_bootstrap_ran_at_import_time():
    """``main.py`` must expose the result of the eviction it performed."""
    mod = _mod()
    assert isinstance(mod._EVICTED_MODULES, list)


def test_loaded_core_package_comes_from_this_plugin():
    """Whatever `core` resolved to must be *our* files."""
    mod = _mod()
    core = sys.modules.get("core")
    assert core is not None
    origin = mod._module_origin(core)
    assert origin is not None and mod._is_inside_plugin_dir(origin)


# --------------------------------------------------------------------------
# keep the eviction list honest
# --------------------------------------------------------------------------

# 允许缩进，因为 `_cmd_update` 里的 `from scraper…` 是函数内导入。
_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)")


def test_internal_packages_covers_every_first_party_absolute_import():
    """Add a new subpackage to main.py without registering it? This fails.

    Anything main.py imports as a *bare top-level* name gets left behind in
    ``sys.modules`` across a plugin reload unless it is listed in
    ``_INTERNAL_PACKAGES`` — so the list is a correctness requirement, not a
    convenience.
    """
    mod = _mod()
    src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")

    roots: set[str] = set()
    for line in src.splitlines():
        match = _IMPORT_RE.match(line)
        if match:
            roots.add(match.group(1))

    external = set(sys.stdlib_module_names) | {"astrbot", "__future__"}
    first_party = roots - external

    assert first_party <= set(mod._INTERNAL_PACKAGES), (
        f"main.py imports {sorted(first_party - set(mod._INTERNAL_PACKAGES))} as a "
        f"bare top-level name; add it to _INTERNAL_PACKAGES or it will survive "
        f"plugin reloads"
    )
    assert first_party, "expected main.py to import at least one of our subpackages"


def test_bootstrap_runs_before_the_imports_it_protects():
    """The eviction must happen before `from core… import`, not after."""
    src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert src.index("_EVICTED_MODULES: list[str] = _evict_stale_modules()") < src.index(
        "from core.data_loader import"
    )
    assert src.index("sys.path.insert(0, str(_PKG_DIR))") < src.index(
        "from core.data_loader import"
    )
