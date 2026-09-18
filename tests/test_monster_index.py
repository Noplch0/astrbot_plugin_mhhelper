"""Unit tests for core.monster_index."""
import pytest

from core.errors import InvalidGame, MonsterNotFound
from core.monster_index import MonsterIndex

from ._setup import install_fake_loader


@pytest.fixture(autouse=True)
def fake_loader(monkeypatch):
    install_fake_loader(monkeypatch)


def test_lookup_zh_exact():
    idx = MonsterIndex()
    idx.reload("mhworld")
    mid, m, g = idx.lookup("雌火龙")
    assert mid == "test-rathian"
    assert g == "mhworld"
    assert m["species"] == "飞龙种"


def test_lookup_en_exact():
    idx = MonsterIndex()
    idx.reload("mhworld")
    mid, _, _ = idx.lookup("Rathian")
    assert mid == "test-rathian"


def test_lookup_alias():
    idx = MonsterIndex()
    idx.reload("mhworld")
    mid, _, _ = idx.lookup("陆之女王")
    assert mid == "test-rathian"


def test_lookup_substring():
    idx = MonsterIndex()
    idx.reload("mhworld")
    mid, _ = idx.lookup("雌火")[:2]
    assert mid == "test-rathian"


def test_lookup_not_found_raises():
    idx = MonsterIndex()
    idx.reload("mhworld")
    with pytest.raises(MonsterNotFound) as ei:
        idx.lookup("不存在的怪物XYZ")
    assert isinstance(ei.value.suggestions, list)


def test_disabled_game_raises():
    from core.errors import GameDisabled
    idx = MonsterIndex()
    idx.configure({"mhworld": False})
    # Do not pre-reload; _ensure_game should raise immediately
    with pytest.raises(GameDisabled):
        idx.list_monsters("mhworld")


def test_invalid_game_raises():
    idx = MonsterIndex()
    with pytest.raises(InvalidGame):
        idx.list_monsters("invalid")