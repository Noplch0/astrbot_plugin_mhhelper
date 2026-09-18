"""Unit tests for core.skill_index."""
import pytest

from core.errors import SkillNotFound
from core.skill_index import SkillIndex

from ._setup import install_fake_loader


@pytest.fixture(autouse=True)
def fake_loader(monkeypatch):
    install_fake_loader(monkeypatch)


def test_lookup_zh():
    idx = SkillIndex()
    idx.reload("mhworld")
    sid, s, g = idx.lookup("攻击力强化")
    assert sid == "test-attack"
    assert len(s["levels"]) == 3


def test_lookup_en():
    idx = SkillIndex()
    idx.reload("mhworld")
    sid, _, _ = idx.lookup("Attack Boost")
    assert sid == "test-attack"


def test_lookup_missing_raises():
    idx = SkillIndex()
    idx.reload("mhworld")
    with pytest.raises(SkillNotFound):
        idx.lookup("不存在的技能XYZ")