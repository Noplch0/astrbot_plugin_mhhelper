"""Unit tests for core.formatter.

v0.3.6 collapsed the per-topic renderers into a single
:func:`render_monster_report` (怪物名 → 属性弱点 → 肉质表 → 状态异常累积值) and
dropped the emoji from every heading. These tests pin the report's section order,
the "top two weaknesses" rule, the transposed ailment table, and the name
fallback that keeps internal ids out of the UI.
"""
from __future__ import annotations

import unicodedata

from core.formatter import (
    _ailments_section,
    _display_name,
    _element_weakness,
    _weakness_section,
    render_help,
    render_monster_report,
    render_skill,
)

#: 11 列表头（部位/状态 + 9 个数值列，最后一个是 kiranico 标着「麻」实为晕厥的列）
MEAT_HEADERS = ["部位", "状态", "斩", "打", "弹", "火", "水", "雷", "冰", "龙", "麻"]

SAMPLE_MONSTER = {
    "id": "ci-huo-long",
    "name_zh": "雌火龙",
    "name_en": "Rathian",
    "species": "飞龙种",
    "hr_point": 700,
    "base_hp": 4500,
    "icon": "https://example.com/icons/ci-huo-long.webp",
    "meat": {
        "headers": MEAT_HEADERS,
        "rows": [
            # 火0/水15/雷20/冰15/龙30/麻100
            {"part": "头部", "state": "通常", "values": [70, 75, 65, 0, 15, 20, 15, 30, 100]},
            # 火12/水5/雷20/冰3/龙0/麻0
            {"part": "躯干", "state": "通常", "values": [35, 30, 25, 12, 5, 20, 3, 0, 0]},
        ],
    },
    "ailments": {"毒": 250, "睡眠": 150, "麻痹": 180, "爆破异常": 70, "昏厥": 120, "减气": 225},
    "rewards": {"剥取": [{"item": "鳞", "rate": "30%"}]},
}


def _has_emoji(text: str) -> bool:
    return any(unicodedata.category(ch) == "So" for ch in text)


def _table_block(txt: str, after: str = "") -> list[str]:
    lines = txt.split(after, 1)[1].splitlines() if after else txt.splitlines()
    start = next(i for i, l in enumerate(lines) if l.lstrip().startswith("|"))
    end = start
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    return lines[start:end]


def _report(monster: dict) -> str:
    return render_monster_report(monster, "mhwilds")


# --------------------------------------------------------------------------
# 标题与 emoji
# --------------------------------------------------------------------------


def test_report_starts_with_the_monster_name():
    assert _report(SAMPLE_MONSTER).startswith("## 雌火龙 (Rathian)\n")


def test_headings_carry_no_emoji():
    """v0.3.6 起标题里不再有任何 emoji（以前是 `### 🍖 雌火龙 — 肉质表`）。"""
    assert not _has_emoji(_report(SAMPLE_MONSTER))
    assert not _has_emoji(render_help())
    assert not _has_emoji(render_skill({"name_zh": "攻击", "levels": []}, "mhwilds"))


def test_name_without_chinese_falls_back_to_english():
    md = render_monster_report({"id": "x", "name_en": "Aknosom"}, "mhrise")
    assert md.startswith("## Aknosom")


# --------------------------------------------------------------------------
# 分节顺序：属性弱点 → 肉质表 → 状态异常
# --------------------------------------------------------------------------


def test_sections_appear_in_the_required_order():
    md = _report(SAMPLE_MONSTER)
    weak = md.index("### 属性弱点")
    meat = md.index("### 肉质表")
    ail = md.index("### 状态异常累积值")
    assert weak < meat < ail


def test_every_section_is_a_heading():
    md = _report(SAMPLE_MONSTER)
    for heading in ("### 属性弱点（最强两项）", "### 肉质表", "### 状态异常累积值"):
        assert heading in md


# --------------------------------------------------------------------------
# 属性弱点：只留最强两项
# --------------------------------------------------------------------------


def test_element_weakness_keeps_only_the_top_two():
    md = _report(SAMPLE_MONSTER)
    section = md.split("### 属性弱点")[1].split("### 肉质表")[0]
    bullets = [l for l in section.splitlines() if l.startswith("- ")]
    # 各部位最大值：火12 水15 雷20 冰15 龙30 → 龙30 / 雷20
    assert bullets == ["- **龙**：30", "- **雷**：20"]


def test_element_weakness_matches_the_users_example():
    """用户给的例子：煌雷龙只展示数值最大的冰(25)、水(20)。"""
    monster = {
        "name_zh": "煌雷龙",
        "meat": {
            "headers": MEAT_HEADERS,
            "rows": [
                # 火5 水20 雷0 冰25 龙5
                {"part": "头部", "state": "通常", "values": [60, 65, 50, 5, 20, 0, 25, 5, 100]},
            ],
        },
    }
    section = "\n".join(_weakness_section(monster))
    assert "- **冰**：25" in section
    assert "- **水**：20" in section
    assert "- **火**：5" not in section
    assert "- **龙**：5" not in section


def test_zero_elements_are_not_weaknesses():
    monster = {
        "name_zh": "X",
        "meat": {"headers": MEAT_HEADERS,
                 "rows": [{"part": "头", "state": "通常", "values": [1, 1, 1, 0, 0, 0, 8, 0, 0]}]},
    }
    assert _element_weakness(monster) == [("冰", 8)]


def test_all_zero_elements_say_so():
    monster = {
        "name_zh": "X",
        "meat": {"headers": MEAT_HEADERS,
                 "rows": [{"part": "头", "state": "通常", "values": [1, 1, 1, 0, 0, 0, 0, 0, 0]}]},
    }
    section = "\n".join(_weakness_section(monster))
    assert "无属性弱点" in section


def test_the_stun_column_never_counts_as_an_element():
    """肉质表最后一列「麻」的数值其实是晕厥，不能出现在属性弱点里。"""
    monster = {
        "name_zh": "X",
        "meat": {"headers": MEAT_HEADERS,
                 "rows": [{"part": "头", "state": "通常", "values": [1, 1, 1, 0, 0, 0, 0, 0, 999]}]},
    }
    section = "\n".join(_weakness_section(monster))
    assert "999" not in section
    assert "**麻**" not in section


def test_equal_values_sort_by_a_fixed_element_order():
    monster = {
        "name_zh": "X",
        "meat": {"headers": MEAT_HEADERS,
                 "rows": [{"part": "头", "state": "通常", "values": [1, 1, 1, 20, 20, 20, 20, 20, 0]}]},
    }
    assert [k for k, _ in _element_weakness(monster)] == ["火", "水", "雷", "冰", "龙"]


# --------------------------------------------------------------------------
# 肉质表
# --------------------------------------------------------------------------


def test_meat_table_is_still_a_normal_table():
    block = _table_block(_report(SAMPLE_MONSTER), "### 肉质表")
    assert len(block) == 2 + 2, "表头 + 分隔行 + 2 行数据"
    header, separator, first, _ = block
    assert header.startswith("| 部位 | 状态 | 斩 |")
    assert set(separator.replace("|", " ").split()) == {":---", "---:"}
    assert first.startswith("| 头部 | 通常 | 70 |")


def test_meat_table_truncates_and_says_so():
    monster = dict(SAMPLE_MONSTER)
    monster["meat"] = {
        "headers": MEAT_HEADERS,
        "rows": [{"part": f"p{i}", "state": "通常", "values": [1, 1, 1, 1, 1, 1, 1, 1, 1]}
                 for i in range(40)],
    }
    md = render_monster_report(monster, "mhwilds", max_rows=5)
    assert md.count("| p") == 5
    assert f"共 40 行，本条消息仅展示前 5 行。" in md


def test_meat_children_status_is_filled_in():
    """沿用 v0.1.0 的兼容：只有 part 没有 state 时补「通常」。"""
    monster = {"name_zh": "X", "meat": {"headers": ["部位", "斩"], "rows": [{"part": "头", "values": [9]}]}}
    md = render_monster_report(monster, "mhwilds")
    assert "| 头 | 9 |" in md


# --------------------------------------------------------------------------
# 状态异常：横向表格
# --------------------------------------------------------------------------


def test_ailments_are_transposed_into_a_two_row_table():
    block = _table_block(_report(SAMPLE_MONSTER), "### 状态异常累积值")
    assert len(block) == 3, "表头（=异常种类）+ 分隔行 + 数值行"
    labels, _separator, values = block
    assert labels == "| 毒 | 眠 | 麻 | 爆 | 晕 | 减气 |"
    assert values == "| 250 | 150 | 180 | 70 | 120 | 225 |"


def test_ailment_columns_are_all_right_aligned():
    _labels, separator, _values = _table_block(_report(SAMPLE_MONSTER), "### 状态异常累积值")
    assert set(separator.replace("|", " ").split()) == {"---:"}


def test_ailment_values_survive():
    md = _report(SAMPLE_MONSTER)
    for value in SAMPLE_MONSTER["ailments"].values():
        assert str(value) in md


def test_ailment_labels_are_single_characters():
    section = "\n".join(_ailments_section(SAMPLE_MONSTER))
    assert "**毒**" not in section, "横向表格里标签就在表头，不该再有加粗行"


def test_unknown_ailment_keys_pass_through():
    section = "\n".join(_ailments_section({"name_zh": "X", "ailments": {"怪异化": 99}}))
    assert "| 怪异化 |" in section
    assert "| 99 |" in section


def test_mhworld_english_ailment_keys_are_labelled():
    section = "\n".join(_ailments_section(
        {"name_zh": "X", "ailments": {"Mount": 50, "Captures": 150, "Stamina": 225}}
    ))
    assert "| 骑乘 | 捕获 | 减气 |" in section


def test_missing_ailments_say_so():
    section = "\n".join(_ailments_section({"name_zh": "X"}))
    assert "该作品暂无状态异常数据。" in section


# --------------------------------------------------------------------------
# 无数据 / 名字兜底
# --------------------------------------------------------------------------


def test_report_without_meat_data():
    md = render_monster_report({"name_zh": "X"}, "mhwilds")
    assert "### 肉质表" in md
    assert "暂无肉质数据" in md
    assert "无属性弱点" in md


def test_display_name_prefers_chinese_then_english_then_id():
    assert _display_name({"name_zh": "伞鸟", "name_en": "Aknosom", "id": "1"}) == "伞鸟 (Aknosom)"
    assert _display_name({"name_zh": "伞鸟", "id": "1"}) == "伞鸟"
    assert _display_name({"name_en": "Aknosom", "id": "1"}) == "Aknosom"
    assert _display_name({"id": "1301934382"}) == "1301934382"


def test_display_name_does_not_repeat_identical_names():
    assert _display_name({"name_zh": "Rathian", "name_en": "Rathian"}) == "Rathian"


def test_blank_names_are_treated_as_missing():
    assert _display_name({"name_zh": "  ", "name_en": " Aknosom ", "id": "1"}) == "Aknosom"


# --------------------------------------------------------------------------
# 帮助 / 技能
# --------------------------------------------------------------------------


def test_render_help_describes_the_merged_command():
    txt = render_help()
    assert "/mh 怪物 <名字> [作品]" in txt
    assert "属性弱点" in txt and "肉质表" in txt
    # 已删除的功能不能再出现在帮助里
    for gone in ("怪物列表", "技能列表", "/mh 素材", "/mh 肉质", "/mh 弱点"):
        assert gone not in txt, f"{gone} 已删除，帮助里不该还有"


def test_render_skill_uses_list_style():
    s = {"name_zh": "攻击力强化", "name_en": "Attack Boost",
         "levels": [{"lv": 1, "effect": "+3"}, {"lv": 2, "effect": "+6"}]}
    txt = render_skill(s, "mhwilds")
    body = [l for l in txt.splitlines() if l.strip()]
    assert body[0] == "## 攻击力强化 (Attack Boost) — 怪物猎人:荒野"
    assert body[1] == "- **Lv 1** +3"
    assert body[2] == "- **Lv 2** +6"


def test_render_skill_without_levels():
    assert "暂无" in render_skill({"name_zh": "X"}, "mhwilds")


def test_render_skill_english_only_name():
    """崛起/世界的技能名以前会显示成内部 id。"""
    txt = render_skill({"id": "rmZ5b", "name_en": "Poison Resistance", "levels": []}, "mhworld")
    assert txt.startswith("## Poison Resistance")
    assert "rmZ5b" not in txt
