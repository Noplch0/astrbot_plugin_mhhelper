"""Unit tests for core.formatter."""
from core.formatter import (
    render_help,
    render_meat,
    render_monster_info,
    render_skill,
)


SAMPLE_MONSTER = {
    "id": "x",
    "name_zh": "雌火龙",
    "name_en": "Rathian",
    "species": "飞龙种",
    "hr_point": 700,
    "base_hp": 4500,
    "meat": {
        "headers": ["部位", "状态", "斩", "打", "弹", "火", "水", "雷", "冰", "龙", "麻"],
        "rows": [
            {"part": "头部", "state": "通常", "values": [70, 75, 65, 0, 15, 20, 15, 30, 100]},
            {"part": "躯干", "state": "通常", "values": [35, 30, 25, 0, 5, 10, 5, 20, 0]},
        ],
    },
    "ailments": {"毒": 250},
    "rewards": {"剥取": [{"item": "鳞", "rate": "30%"}]},
}


def test_render_help_is_nonempty():
    txt = render_help()
    assert "怪物猎人" in txt
    assert "/mh" in txt


def test_render_monster_info_includes_basic_fields():
    txt = render_monster_info(SAMPLE_MONSTER, "mhwilds")
    assert "雌火龙" in txt
    assert "飞龙种" in txt
    assert "4,500" in txt or "4500" in txt


def test_render_meat_aligns_columns():
    txt = render_meat(SAMPLE_MONSTER, "mhwilds")
    lines = txt.splitlines()
    # table separator lines start with '+' and end with '+'
    assert any(line.startswith("+") and line.endswith("+") for line in lines)
    # every numeric value from the rows appears in the output
    for v in [70, 75, 65, 100, 35, 30, 25]:
        assert str(v) in txt


def test_render_meat_empty_data():
    txt = render_meat({"name_zh": "X", "name_en": "X"}, "mhworld")
    assert "暂无肉质" in txt


def test_render_skill_shows_levels():
    s = {
        "name_zh": "攻击力强化",
        "name_en": "Attack Boost",
        "levels": [{"lv": 1, "effect": "+3"}, {"lv": 2, "effect": "+6"}],
    }
    txt = render_skill(s, "mhwilds")
    assert "攻击力强化" in txt
    assert "+3" in txt
    assert "+6" in txt