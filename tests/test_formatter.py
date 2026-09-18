"""Unit tests for core.formatter.

The formatter's contract changed in v0.3.0: every ``render_*`` now returns
**markdown** (headings / bullets / GFM pipe tables), and the plain-text form is
produced downstream by ``core.render.markdown_to_plaintext``. These tests pin
both the markdown shape and the user-visible strings.
"""
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


def _table_block(txt: str) -> list[str]:
    lines = txt.splitlines()
    start = next(i for i, l in enumerate(lines) if l.lstrip().startswith("|"))
    end = start
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    return lines[start:end]


# --------------------------------------------------------------------------
# 基本内容
# --------------------------------------------------------------------------


def test_render_help_is_nonempty():
    txt = render_help()
    assert "怪物猎人" in txt
    assert "/mh" in txt


def test_render_monster_info_includes_basic_fields():
    txt = render_monster_info(SAMPLE_MONSTER, "mhwilds")
    assert "雌火龙" in txt
    assert "飞龙种" in txt
    assert "4,500" in txt or "4500" in txt


def test_render_meat_includes_values():
    txt = render_meat(SAMPLE_MONSTER, "mhwilds")
    lines = txt.splitlines()
    # No heavy ASCII borders — the table is markdown, not `+---+`.
    assert not any(line.startswith("+") and line.endswith("+") for line in lines)
    assert "部位" in txt
    assert "斩" in txt
    # every numeric value from the rows appears in the output
    for v in [70, 75, 65, 100, 35, 30, 25]:
        assert str(v) in txt


def test_render_skill_uses_list_style():
    s = {
        "name_zh": "攻击力强化",
        "name_en": "Attack Boost",
        "levels": [{"lv": 1, "effect": "+3"}, {"lv": 2, "effect": "+6"}],
    }
    txt = render_skill(s, "mhwilds")
    assert "攻击力强化" in txt
    assert "+3" in txt
    assert "+6" in txt
    assert "Lv 1" in txt
    assert "Lv 2" in txt
    assert not any(line.startswith("+") and line.endswith("+") for line in txt.splitlines())


def test_render_meat_empty_data():
    txt = render_meat({"name_zh": "X", "name_en": "X"}, "mhworld")
    assert "暂无肉质" in txt


def test_render_skill_no_data():
    s = {"name_zh": "X", "name_en": "X"}
    txt = render_skill(s, "mhwilds")
    assert "暂无" in txt or "X" in txt


# --------------------------------------------------------------------------
# markdown 契约
# --------------------------------------------------------------------------


def test_render_meat_emits_gfm_pipe_table():
    txt = render_meat(SAMPLE_MONSTER, "mhwilds")
    block = _table_block(txt)
    assert len(block) == 2 + 2, "表头 + 分隔行 + 2 行数据"
    header, separator, first_row, _second = block
    assert header.startswith("| 部位 | 状态 | 斩 |")
    # 分隔行只由对齐标记组成：文字列左对齐、肉质数值列右对齐
    assert set(separator.replace("|", " ").split()) == {":---", "---:"}
    assert separator.startswith("| :--- | :--- | ---:")
    assert first_row.startswith("| 头部 | 通常 | 70 |")


def test_render_skill_lines_are_markdown_bullets():
    s = {
        "name_zh": "攻击力强化",
        "name_en": "Attack Boost",
        "levels": [{"lv": 1, "effect": "+3"}, {"lv": 2, "effect": "+6"}],
    }
    body = [l for l in render_skill(s, "mhwilds").splitlines() if l.strip()]
    assert body[0].startswith("## 📘")
    assert body[1] == "- **Lv 1** +3"
    assert body[2] == "- **Lv 2** +6"


def test_render_help_is_markdown():
    txt = render_help()
    assert txt.startswith("## 🎮")
    assert "### 怪物" in txt
    assert "- `/mh 肉质 <名字> [作品]`" in txt
