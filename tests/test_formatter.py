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
    render_weak,
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


# --------------------------------------------------------------------------
# 弱点 / 状态异常（v0.3.5 起的文案约定）
# --------------------------------------------------------------------------

#: 完整的异常表，键名与 kiranico 一致。
FULL_AILMENTS = {
    "毒": 150, "睡眠": 150, "麻痹": 300,
    "爆破异常": 70, "昏厥": 150, "减气": 225,
}


def _weak(monster: dict) -> str:
    return render_weak(monster, "mhwilds")


def test_ailment_labels_are_single_characters():
    txt = _weak({"name_zh": "煌雷龙", "ailments": dict(FULL_AILMENTS)})
    body = [l for l in txt.splitlines() if l.startswith("- ")]
    assert body == [
        "- **毒**：150",
        "- **眠**：150",
        "- **麻**：300",
        "- **爆**：70",
        "- **晕**：150",
        "- **减气**：225",  # 减气保持不变
    ]


def test_ailment_values_are_preserved():
    txt = _weak({"name_zh": "X", "ailments": dict(FULL_AILMENTS)})
    for value in FULL_AILMENTS.values():
        assert str(value) in txt


def test_unknown_ailment_keys_pass_through():
    """没登记过的键宁可长一点，也不能被丢掉。"""
    txt = _weak({"name_zh": "X", "ailments": {"怪异化": 99}})
    assert "- **怪异化**：99" in txt


def test_english_ailment_keys_from_mhworld_are_labelled():
    """世界的 kiranico 页混进了英文键。"""
    txt = _weak({"name_zh": "X", "ailments": {"Mount": 50, "Captures": 150, "Stamina": 225}})
    assert "- **骑乘**：50" in txt
    assert "- **捕获**：150" in txt
    assert "- **减气**：225" in txt


def test_elemental_weakness_uses_only_the_five_elements():
    """肉质表最后一列的「麻」数值其实是晕厥，不能当成属性弱点。"""
    txt = _weak(SAMPLE_MONSTER)
    section = txt.split("属性弱点概览", 1)[1]
    # SAMPLE_MONSTER 两行的属性值是 [0,15,20,15,30,100] / [0,5,10,5,20,0]
    assert "- **火**：0" in section
    assert "- **水**：15" in section
    assert "- **雷**：20" in section
    assert "- **冰**：15" in section
    assert "- **龙**：30" in section
    assert "**麻**" not in section, "麻（=晕厥）不属于属性弱点，这一行必须没有"
    assert "100" not in section, "100 是那一列「麻」的最大值，删掉后不该再出现"


def test_elemental_weakness_takes_the_max_across_parts():
    monster = {
        "name_zh": "X",
        "meat": {
            "headers": ["部位", "状态", "斩", "打", "弹", "火", "水", "雷", "冰", "龙", "麻"],
            "rows": [
                {"part": "头", "state": "通常", "values": [1, 1, 1, 5, 25, 0, 10, 0, 999]},
                {"part": "身", "state": "通常", "values": [1, 1, 1, 12, 5, 20, 3, 0, 0]},
            ],
        },
    }
    txt = render_weak(monster, "mhwilds")
    assert "- **火**：12" in txt
    assert "- **水**：25" in txt
    assert "- **雷**：20" in txt
    assert "999" not in txt


def test_render_weak_without_ailments():
    txt = render_weak({"name_zh": "X"}, "mhrise")
    assert "该作品暂无状态异常数据。" in txt
    assert "属性弱点概览" not in txt


def test_render_weak_keeps_the_monster_name_heading():
    txt = _weak({"name_zh": "煌雷龙", "ailments": {"毒": 1}})
    assert txt.startswith("## ⚔️ 煌雷龙")
