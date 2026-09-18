"""Where the plugin is allowed to write its runtime state.

AstrBot's plugin dev guide states that persistent data must live under
AstrBot's own ``data/`` directory (``data/plugin_data/<plugin name>/``) and
**not** in the plugin directory, because a plugin update or reinstall replaces
the plugin directory wholesale.

These tests pin the whole resolution chain, the ``get_astrbot_data_path()``
call the spec mandates, and the one-time migration of the legacy
plugin-local ``plugin_data/user_last_game.json``.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from tests import _astrbot_fake
from tests._astrbot_fake import REPO, install

PLUGIN_NAME = "astrbot_plugin_mhhelper"

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _install_fake_path_api(monkeypatch, data_root: Path) -> None:
    """Register a fake ``astrbot.core.utils.astrbot_path`` into ``sys.modules``.

    ``main.py`` imports ``get_astrbot_data_path`` *lazily* (inside the method),
    so injecting it here is enough — no reimport needed.
    """
    install()
    core_pkg = sys.modules["astrbot.core"]
    utils = types.ModuleType("astrbot.core.utils")
    path_mod = types.ModuleType("astrbot.core.utils.astrbot_path")
    path_mod.get_astrbot_data_path = lambda: str(data_root)
    utils.astrbot_path = path_mod

    monkeypatch.setattr(core_pkg, "utils", utils, raising=False)
    monkeypatch.setitem(sys.modules, "astrbot.core.utils", utils)
    monkeypatch.setitem(sys.modules, "astrbot.core.utils.astrbot_path", path_mod)


def _remove_fake_path_api(monkeypatch) -> None:
    """Make ``import astrbot.core.utils.astrbot_path`` fail again."""
    for name in ("astrbot.core.utils.astrbot_path", "astrbot.core.utils"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys.modules["astrbot.core"], "utils", None, raising=False)


def _bare_plugin(data_root: Path):
    """Build a plugin instance without running ``__init__``.

    ``__init__`` resolves the state directory from the *real* plugin location,
    which would leak a ``plugin_data/`` into the repo during tests. Building a
    bare instance lets each test choose ``_data_root`` freely.
    """
    mod = _astrbot_fake.load_plugin()
    plugin = mod.MHHelperPlugin.__new__(mod.MHHelperPlugin)
    plugin._data_root = data_root
    plugin.config = plugin._default_config()
    plugin._user_game_cache = {}
    return mod, plugin


def _plugin_dir(root: Path) -> Path:
    """``<root>/data/plugins/<plugin name>`` — the real install layout."""
    return root / "data" / "plugins" / PLUGIN_NAME


# --------------------------------------------------------------------------
# resolution order
# --------------------------------------------------------------------------


def test_official_api_is_used_when_available(tmp_path, monkeypatch):
    """``Path(get_astrbot_data_path()) / "plugin_data" / <name>`` — verbatim."""
    data_root = tmp_path / "astrbot" / "data"
    _install_fake_path_api(monkeypatch, data_root)
    _, plugin = _bare_plugin(_plugin_dir(tmp_path / "astrbot"))

    resolved = plugin._plugin_state_dir()

    assert resolved == data_root / "plugin_data" / PLUGIN_NAME
    assert resolved.is_dir(), "the state directory must be created on demand"


def test_official_api_beats_path_sniffing(tmp_path, monkeypatch):
    """A wrong-looking plugin location must not override the official API."""
    data_root = tmp_path / "official" / "data"
    _install_fake_path_api(monkeypatch, data_root)
    # Deliberately *not* <root>/data/plugins/<name>; sniffing would give
    # tmp_path/somewhere/plugin_data, which must lose.
    _, plugin = _bare_plugin(tmp_path / "somewhere" / "else")

    assert plugin._plugin_state_dir() == data_root / "plugin_data" / PLUGIN_NAME


def test_derived_dir_when_api_missing(tmp_path, monkeypatch):
    """No official API (older AstrBot) → derive it from the install layout."""
    _remove_fake_path_api(monkeypatch)
    install_root = tmp_path / "AstrBot"
    _, plugin = _bare_plugin(_plugin_dir(install_root))

    resolved = plugin._plugin_state_dir()

    assert resolved == install_root / "data" / "plugin_data" / PLUGIN_NAME
    assert resolved.is_dir()


def test_derived_dir_declines_when_layout_is_unexpected(tmp_path, monkeypatch):
    """A repo checkout (``<repo>/core`` …) must not invent ``../plugin_data``."""
    _remove_fake_path_api(monkeypatch)
    _, plugin = _bare_plugin(tmp_path / "somewhere" / "else")

    assert plugin._derived_state_dir() is None


def test_falls_back_to_plugin_dir_as_last_resort(tmp_path, monkeypatch):
    """Both official routes unavailable → keep working, inside the plugin."""
    _remove_fake_path_api(monkeypatch)
    data_root = tmp_path / "weird" / "layout"
    _, plugin = _bare_plugin(data_root)

    resolved = plugin._plugin_state_dir()

    assert resolved == data_root / "plugin_data"
    assert resolved.is_dir()


def test_undeletable_official_dir_falls_through(tmp_path, monkeypatch):
    """If the official directory cannot be created, try the next resolver."""
    blocked = tmp_path / "official" / "data"
    _install_fake_path_api(monkeypatch, blocked)
    install_root = tmp_path / "AstrBot"
    _, plugin = _bare_plugin(_plugin_dir(install_root))

    real_mkdir = Path.mkdir

    def fake_mkdir(self, *args, **kwargs):
        if blocked in self.parents or self == blocked:
            raise OSError("read-only filesystem")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)

    assert plugin._plugin_state_dir() == install_root / "data" / "plugin_data" / PLUGIN_NAME


# --------------------------------------------------------------------------
# state file constants
# --------------------------------------------------------------------------


def test_state_constants_match_documented_layout():
    mod = _astrbot_fake.load_plugin()
    assert mod.STATE_FILENAME == "user_last_game.json"
    assert mod.LEGACY_STATE_DIRNAME == "plugin_data"
    assert mod.PLUGIN_NAME == PLUGIN_NAME


def test_main_py_declares_the_official_api_import():
    """Regression guard: the official API call must not be dropped."""
    src = (REPO / "main.py").read_text(encoding="utf-8")
    assert "from astrbot.core.utils.astrbot_path import get_astrbot_data_path" in src
    assert '"plugin_data"' in src


# --------------------------------------------------------------------------
# legacy migration
# --------------------------------------------------------------------------


def _with_state(tmp_path, monkeypatch, legacy_payload: str | None):
    """Return ``(plugin, new_path, legacy_path)`` with an official state dir."""
    data_root = tmp_path / "AstrBot" / "data"
    _install_fake_path_api(monkeypatch, data_root)
    mod, plugin = _bare_plugin(_plugin_dir(tmp_path / "AstrBot"))
    new_path = plugin._plugin_state_dir() / mod.STATE_FILENAME
    plugin._state_path = new_path

    legacy = plugin._legacy_state_path()
    if legacy_payload is not None:
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(legacy_payload, encoding="utf-8")
    return plugin, new_path, legacy


def test_legacy_state_is_read(tmp_path, monkeypatch):
    plugin, _, legacy = _with_state(
        tmp_path, monkeypatch, json.dumps({"10001": "mhrise"})
    )
    assert plugin._load_user_state() == {"10001": "mhrise"}
    assert legacy.is_file(), "loading must not destroy the old file"


def test_legacy_state_migrates_on_save(tmp_path, monkeypatch):
    plugin, new_path, legacy = _with_state(
        tmp_path, monkeypatch, json.dumps({"10001": "mhrise"})
    )
    plugin._user_game_cache = plugin._load_user_state()

    plugin._save_user_state()

    assert new_path.is_file()
    assert json.loads(new_path.read_text(encoding="utf-8")) == {"10001": "mhrise"}
    assert not legacy.exists(), "the migrated legacy file should be cleaned up"
    assert not legacy.parent.exists(), "and the now-empty directory removed"


def test_new_path_wins_over_legacy(tmp_path, monkeypatch):
    plugin, new_path, legacy = _with_state(
        tmp_path, monkeypatch, json.dumps({"10001": "mhrise"})
    )
    new_path.write_text(json.dumps({"10001": "mhwilds"}), encoding="utf-8")

    assert plugin._load_user_state() == {"10001": "mhwilds"}


def test_corrupt_legacy_state_is_ignored(tmp_path, monkeypatch):
    plugin, _, _ = _with_state(tmp_path, monkeypatch, "{ not json")
    assert plugin._load_user_state() == {}


def test_non_dict_state_is_ignored(tmp_path, monkeypatch):
    plugin, _, _ = _with_state(tmp_path, monkeypatch, json.dumps(["nope"]))
    assert plugin._load_user_state() == {}


def test_values_are_coerced_to_strings(tmp_path, monkeypatch):
    plugin, _, _ = _with_state(tmp_path, monkeypatch, json.dumps({"10001": 42}))
    assert plugin._load_user_state() == {"10001": "42"}


def test_no_state_anywhere_is_an_empty_cache(tmp_path, monkeypatch):
    plugin, _, _ = _with_state(tmp_path, monkeypatch, None)
    assert plugin._load_user_state() == {}


def test_fallback_keeps_its_own_file(tmp_path, monkeypatch):
    """In fallback mode the "legacy" path *is* the live path — never delete it."""
    _remove_fake_path_api(monkeypatch)
    data_root = tmp_path / "weird" / "layout"
    mod, plugin = _bare_plugin(data_root)
    plugin._state_path = plugin._plugin_state_dir() / mod.STATE_FILENAME
    plugin._user_game_cache = {"10001": "mhrise"}

    plugin._save_user_state()

    assert plugin._state_path.is_file()
    assert json.loads(plugin._state_path.read_text(encoding="utf-8")) == {
        "10001": "mhrise"
    }


def test_legacy_dir_with_other_files_survives(tmp_path, monkeypatch):
    """Only our own file is removed; a shared directory is left alone."""
    plugin, _, legacy = _with_state(
        tmp_path, monkeypatch, json.dumps({"10001": "mhrise"})
    )
    (legacy.parent / "keepme.txt").write_text("hi", encoding="utf-8")

    plugin._user_game_cache = plugin._load_user_state()
    plugin._save_user_state()

    assert not legacy.exists()
    assert legacy.parent.is_dir()
    assert (legacy.parent / "keepme.txt").is_file()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
