"""Listing-page parsing: one rule per kiranico page, verified against trimmed HTML.

Five pages, five different conventions — but all keyed by the same id that
appears in ``data/monsters|skills/<game>.json``, which is what lets the plugin
ship icons and Chinese names with the data instead of fetching them per query.

The fixtures are trimmed copies of the real markup, so a site change shows up
here as a failing test rather than as a missing icon / an id leaking into the
UI in production.
"""
from __future__ import annotations

from scraper.listing import (
    MONSTER_INDEX_URLS,
    MONSTER_PARSERS,
    SKILL_INDEX_URLS,
    SKILL_PARSERS,
    monster_icons,
    monster_names,
    parse_mhrise_monsters,
    parse_mhwilds_monsters,
    parse_mhworld_monsters,
    parse_monsters,
    skill_names,
)

# --------------------------------------------------------------------------
# 荒野：<img src="…/em_icon/EM0001_00_0.webp"> 后跟 <a …><span>雌火龙</span></a>
# --------------------------------------------------------------------------

MHWILDS_HTML = """
<tr><td class="p-2">
  <img alt="" loading="lazy" width="96" src="https://mhwilds.kiranico.net/em_icon/EM0001_00_0.webp"/>
</td><td class="p-2"><a class="text" href="/zh/data/monsters/ci-huo-long"><span>雌火龙</span></a></td></tr>
<tr><td class="p-2">
  <img alt="" loading="lazy" width="96" src="https://mhwilds.kiranico.net/em_icon/EM0160_00_0.webp"/>
</td><td class="p-2"><a class="text" href="/zh/data/monsters/suo-ren-long"><span>锁刃龙</span></a></td></tr>
"""


def test_mhwilds_pairs_icon_and_name_with_slug():
    assert parse_mhwilds_monsters(MHWILDS_HTML) == {
        "ci-huo-long": {
            "icon": "https://mhwilds.kiranico.net/em_icon/EM0001_00_0.webp",
            "name": "雌火龙",
        },
        "suo-ren-long": {
            "icon": "https://mhwilds.kiranico.net/em_icon/EM0160_00_0.webp",
            "name": "锁刃龙",
        },
    }


def test_mhwilds_strips_the_inner_span():
    """名字包在 <span> 里，不能把标签带进数据。"""
    for name in monster_names("mhwilds", MHWILDS_HTML).values():
        assert "<" not in name and "span" not in name


def test_mhwilds_ignores_the_index_link_without_a_slug():
    html = '<a href="/zh/data/monsters">怪物</a>' + MHWILDS_HTML
    assert "zh/data/monsters" not in monster_icons("mhwilds", html)


def test_mhwilds_row_without_a_link_does_not_steal_the_next_row():
    html = """
    <img src="https://mhwilds.kiranico.net/em_icon/EM0999_00_0.webp"/>
    <img src="https://mhwilds.kiranico.net/em_icon/EM0001_00_0.webp"/>
    <a href="/zh/data/monsters/ci-huo-long"><span>雌火龙</span></a>
    """
    assert monster_icons("mhwilds", html) == {
        "ci-huo-long": "https://mhwilds.kiranico.net/em_icon/EM0001_00_0.webp"
    }


# --------------------------------------------------------------------------
# 崛起：名字在 <img alt> 上，id 在紧随的链接里，图标是 http 的
# --------------------------------------------------------------------------

MHRISE_HTML = """
<div class="group relative p-4">
  <img src="http://cdn.kiranico.net/file/kiranico/mhrise-web/images/icons/em132_05.png"
       alt="原初形态爵银龙" class="w-full h-full">
  <div class="pt-10 pb-4 text-center"><h3>
    <a href="https://mhrise.kiranico.com/zh/data/monsters/1301934382">
  </h3></div>
</div>
<div class="group relative p-4">
  <img src="http://cdn.kiranico.net/file/kiranico/mhrise-web/images/icons/em091_00.png"
       alt="伞鸟" class="w-full h-full">
  <div class="pt-10 pb-4 text-center"><h3>
    <a href="https://mhrise.kiranico.com/zh/data/monsters/2084266193">
  </h3></div>
</div>
"""


def test_mhrise_pairs_icon_and_alt_name_with_numeric_id():
    assert parse_mhrise_monsters(MHRISE_HTML) == {
        "1301934382": {
            "icon": "https://cdn.kiranico.net/file/kiranico/mhrise-web/images/icons/em132_05.png",
            "name": "原初形态爵银龙",
        },
        "2084266193": {
            "icon": "https://cdn.kiranico.net/file/kiranico/mhrise-web/images/icons/em091_00.png",
            "name": "伞鸟",
        },
    }


def test_mhrise_upgrades_http_icons_to_https():
    """卡片是 https 页面，加载 http 图会被当成混合内容拦掉。"""
    for url in monster_icons("mhrise", MHRISE_HTML).values():
        assert url.startswith("https://")


def test_mhrise_language_switcher_does_not_hijack_the_pairing():
    html = '<a href="https://mhrise.kiranico.com/ar/data/monsters?view=lg">AR</a>' + MHRISE_HTML
    assert len(parse_mhrise_monsters(html)) == 2


def test_mhrise_ignores_cover_art():
    html = ('<img src="https://cdn.kiranico.net/file/kiranico/kiranico-web/covers/1.jpg">'
            + MHRISE_HTML)
    assert len(parse_mhrise_monsters(html)) == 2


# --------------------------------------------------------------------------
# 世界：图标与锚文本分别在两个标签里
# --------------------------------------------------------------------------

MHWORLD_HTML = """
<tr><td><div class="d-flex">
  <img class="img-fluid" width="48"
       src="https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/em105_ID.png">
  <span><a href="https://mhworld.kiranico.com/zh/monsters/wA8F8/ming-deng-long">冥灯龙</a></span>
</div></td>
<td><img src="https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/element_1.png"></td></tr>
<tr><td><div class="d-flex">
  <img class="img-fluid" width="48"
       src="https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/ems061_01_ID.png">
  <span><a href="https://mhworld.kiranico.com/zh/monsters/XYdC6/shou-chan-zu">兽缠族</a></span>
</div></td>
<td><img src="https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/ib_icon.png" width="16"></td></tr>
"""


def test_mhworld_pairs_icon_and_anchor_text_for_large_and_small_monsters():
    assert parse_mhworld_monsters(MHWORLD_HTML) == {
        "wA8F8": {
            "icon": "https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/em105_ID.png",
            "name": "冥灯龙",
        },
        "XYdC6": {
            "icon": "https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/ems061_01_ID.png",
            "name": "兽缠族",
        },
    }


def test_mhworld_ignores_element_and_dlc_badges():
    """element_N.png 是属性图标、ib_icon.png 是冰原徽标，都不是怪物头像。"""
    for url in monster_icons("mhworld", MHWORLD_HTML).values():
        assert "element_" not in url
        assert "ib_icon" not in url


def test_mhworld_without_the_badges_still_pairs_the_same_rows():
    """去掉 element/ib 图标后结果不变 —— 说明配对不依赖它们的数量。"""
    stripped = MHWORLD_HTML.replace(
        '<img src="https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/element_1.png">', ""
    ).replace(
        '<img src="https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/ib_icon.png" width="16">', ""
    )
    assert parse_mhworld_monsters(stripped) == parse_mhworld_monsters(MHWORLD_HTML)


# --------------------------------------------------------------------------
# 技能列表：只有中文名（技能没有图标）
# --------------------------------------------------------------------------

MHRISE_SKILLS_HTML = """
<tr><td class="px-2 py-2">
  <a href="https://mhrise.kiranico.com/zh/data/skills/366824395" class="flex-shrink-0 group block">
    <div class="flex items-center"><div class="ml-3">
      <p class="text-sm font-medium text-sky-500">
        攻击
      </p>
    </div></div>
  </a>
</td></tr>
<tr><td class="px-2 py-2">
  <a href="https://mhrise.kiranico.com/zh/data/skills/381074408" class="flex-shrink-0 group block">
    <div class="flex items-center"><div class="ml-3">
      <p class="text-sm font-medium text-sky-500">
        挑战者
      </p>
    </div></div>
  </a>
</td></tr>
"""

MHWORLD_SKILLS_HTML = """
<tr>
  <td rowspan="4">
    <a href="https://mhworld.kiranico.com/zh/skilltrees/rmZ5b/du-nai-xing">毒耐性</a> </td>
</tr>
<tr>
  <td>
    <a href="https://mhworld.kiranico.com/zh/skilltrees/Mm98b/ma-bi-nai-xing">麻痹耐性</a> </td>
</tr>
"""


def test_mhrise_skill_names_come_from_nested_anchor_text():
    """崛起的技能名嵌在好几层标签里，必须剥干净。"""
    assert skill_names("mhrise", MHRISE_SKILLS_HTML) == {
        "366824395": "攻击",
        "381074408": "挑战者",
    }


def test_mhworld_skill_names_come_from_anchor_text():
    assert skill_names("mhworld", MHWORLD_SKILLS_HTML) == {
        "rmZ5b": "毒耐性",
        "Mm98b": "麻痹耐性",
    }


def test_skills_have_no_icons():
    assert monster_icons("mhrise", MHRISE_SKILLS_HTML) == {}
    assert monster_icons("mhworld", MHWORLD_SKILLS_HTML) == {}


# --------------------------------------------------------------------------
# 分派与常量
# --------------------------------------------------------------------------


def test_parse_monsters_dispatches_per_game():
    assert parse_monsters("mhwilds", MHWILDS_HTML) == parse_mhwilds_monsters(MHWILDS_HTML)
    assert parse_monsters("mhrise", MHRISE_HTML) == parse_mhrise_monsters(MHRISE_HTML)
    assert parse_monsters("mhworld", MHWORLD_HTML) == parse_mhworld_monsters(MHWORLD_HTML)


def test_unknown_game_is_empty():
    assert parse_monsters("mhnowhere", MHWILDS_HTML) == {}
    assert monster_icons("mhnowhere", MHWILDS_HTML) == {}
    assert monster_names("mhnowhere", MHWILDS_HTML) == {}
    assert skill_names("mhnowhere", MHWILDS_HTML) == {}


def test_empty_html_yields_nothing():
    for game in MONSTER_PARSERS:
        assert parse_monsters(game, "") == {}
    for game in SKILL_PARSERS:
        assert skill_names(game, "") == {}


def test_parsers_cover_every_index_url():
    assert set(MONSTER_PARSERS) == set(MONSTER_INDEX_URLS) == {"mhwilds", "mhrise", "mhworld"}
    assert set(SKILL_PARSERS) == set(SKILL_INDEX_URLS) == {"mhrise", "mhworld"}


def test_index_urls_are_the_zh_pages():
    """中文名与图标只在 zh 列表页上，不能退回 /en。"""
    assert MONSTER_INDEX_URLS["mhwilds"] == "https://mhwilds.kiranico.com/zh/data/monsters"
    assert MONSTER_INDEX_URLS["mhrise"] == "https://mhrise.kiranico.com/zh/data/monsters?view=lg"
    assert MONSTER_INDEX_URLS["mhworld"] == "https://mhworld.kiranico.com/zh/monsters"
    assert SKILL_INDEX_URLS["mhrise"] == "https://mhrise.kiranico.com/zh/data/skills"
    assert SKILL_INDEX_URLS["mhworld"] == "https://mhworld.kiranico.com/zh/skilltrees"
