"""Icon scraping: one rule per kiranico site, verified against trimmed pages.

The three sites share nothing — different hosts, file naming and markup — and
the id conventions differ too, but each id matches ``data/monsters/<game>.json``
so the plugin can look an icon up at query time without touching the network.

These fixtures are trimmed copies of the real markup, so a site change shows up
here as a failing test rather than as missing icons in production.
"""
from __future__ import annotations

from scraper.icons import (
    INDEX_URLS,
    PARSERS,
    parse_icons,
    parse_mhrise_icons,
    parse_mhwilds_icons,
    parse_mhworld_icons,
)

# --------------------------------------------------------------------------
# mhwilds: <img src="…/em_icon/EM0001_00_0.webp"> … <a href="/zh/data/monsters/<slug>">
# --------------------------------------------------------------------------

MHWILDS_HTML = """
<tbody>
<tr><td class="p-2">
  <img alt="" loading="lazy" width="96" height="96" src="https://mhwilds.kiranico.net/em_icon/EM0001_00_0.webp"/>
</td><td class="p-2"><a class="text" href="/zh/data/monsters/ci-huo-long">雌火龙</a></td></tr>
<tr><td class="p-2">
  <img alt="" loading="lazy" width="96" height="96" src="https://mhwilds.kiranico.net/em_icon/EM0160_00_0.webp"/>
</td><td class="p-2"><a class="text" href="/zh/data/monsters/suo-ren-long">锁刃龙</a></td></tr>
</tbody>
"""


def test_mhwilds_pairs_icon_with_slug():
    assert parse_mhwilds_icons(MHWILDS_HTML) == {
        "ci-huo-long": "https://mhwilds.kiranico.net/em_icon/EM0001_00_0.webp",
        "suo-ren-long": "https://mhwilds.kiranico.net/em_icon/EM0160_00_0.webp",
    }


def test_mhwilds_ignores_the_index_link_without_a_slug():
    """导航里的 `/zh/data/monsters`（没有 slug）不能被当成怪物。"""
    html = '<a href="/zh/data/monsters">怪物</a>' + MHWILDS_HTML
    assert "zh/data/monsters" not in parse_mhwilds_icons(html)


def test_mhwilds_row_without_a_link_does_not_steal_the_next_row():
    """某一行没有链接时，不能把下一行的链接配给这一行的图标。"""
    html = """
    <img src="https://mhwilds.kiranico.net/em_icon/EM0999_00_0.webp"/>
    <img src="https://mhwilds.kiranico.net/em_icon/EM0001_00_0.webp"/>
    <a href="/zh/data/monsters/ci-huo-long">雌火龙</a>
    """
    assert parse_mhwilds_icons(html) == {
        "ci-huo-long": "https://mhwilds.kiranico.net/em_icon/EM0001_00_0.webp"
    }


# --------------------------------------------------------------------------
# mhrise: <img src="http://cdn…/mhrise-web/images/icons/em###_##.png" alt="…">
# --------------------------------------------------------------------------

MHRISE_HTML = """
<div class="group relative p-4">
  <img src="http://cdn.kiranico.net/file/kiranico/mhrise-web/images/icons/em132_05.png"
       alt="原初形态爵银龙" class="w-full h-full">
  <div class="pt-10 pb-4 text-center"><h3 class="text-sm">
    <a href="https://mhrise.kiranico.com/zh/data/monsters/1301934382">原初形态爵银龙</a>
  </h3></div>
</div>
<div class="group relative p-4">
  <img src="http://cdn.kiranico.net/file/kiranico/mhrise-web/images/icons/em091_00.png"
       alt="伞鸟" class="w-full h-full">
  <div class="pt-10 pb-4 text-center"><h3 class="text-sm">
    <a href="https://mhrise.kiranico.com/zh/data/monsters/2084266193">伞鸟</a>
  </h3></div>
</div>
"""


def test_mhrise_pairs_icon_with_numeric_id():
    assert parse_mhrise_icons(MHRISE_HTML) == {
        "1301934382": "https://cdn.kiranico.net/file/kiranico/mhrise-web/images/icons/em132_05.png",
        "2084266193": "https://cdn.kiranico.net/file/kiranico/mhrise-web/images/icons/em091_00.png",
    }


def test_mhrise_upgrades_http_icons_to_https():
    """卡片是 https 页面，加载 http 图会被当成混合内容拦掉。"""
    for url in parse_mhrise_icons(MHRISE_HTML).values():
        assert url.startswith("https://")


def test_mhrise_language_switcher_does_not_hijack_the_pairing():
    html = '<a href="https://mhrise.kiranico.com/ar/data/monsters?view=lg">AR</a>' + MHRISE_HTML
    icons = parse_mhrise_icons(html)
    assert "ar" not in icons
    assert len(icons) == 2


def test_mhrise_ignores_cover_art():
    """站点封面图（covers/*.jpg）不是怪物图标。"""
    html = ('<img src="https://cdn.kiranico.net/file/kiranico/kiranico-web/covers/1.jpg">'
            + MHRISE_HTML)
    assert len(parse_mhrise_icons(html)) == 2


# --------------------------------------------------------------------------
# mhworld: <img src="…/icon/em105_ID.png"> … <a href="/zh/monsters/<code>/<slug>">
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


def test_mhworld_pairs_large_and_small_monsters():
    assert parse_mhworld_icons(MHWORLD_HTML) == {
        "wA8F8": "https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/em105_ID.png",
        "XYdC6": "https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/ems061_01_ID.png",
    }


def test_mhworld_ignores_element_and_dlc_badges():
    """element_N.png 是属性图标、ib_icon.png 是冰原徽标，都不是怪物头像。"""
    for url in parse_mhworld_icons(MHWORLD_HTML).values():
        assert "element_" not in url
        assert "ib_icon" not in url


def test_mhworld_without_the_badges_still_pairs_the_same_rows():
    """去掉 element/ib 图标后结果不变 —— 说明配对不依赖它们的数量。"""
    stripped = MHWORLD_HTML.replace(
        '<img src="https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/element_1.png">', ""
    ).replace(
        '<img src="https://cdn.kiranico.net/file/kiranico/mhworld-web/mhw/icon/ib_icon.png" width="16">', ""
    )
    assert parse_mhworld_icons(stripped) == parse_mhworld_icons(MHWORLD_HTML)


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------


def test_parse_icons_dispatches_per_game():
    assert parse_icons("mhwilds", MHWILDS_HTML) == parse_mhwilds_icons(MHWILDS_HTML)
    assert parse_icons("mhrise", MHRISE_HTML) == parse_mhrise_icons(MHRISE_HTML)
    assert parse_icons("mhworld", MHWORLD_HTML) == parse_mhworld_icons(MHWORLD_HTML)


def test_parse_icons_unknown_game_is_empty():
    assert parse_icons("mhnowhere", MHWILDS_HTML) == {}


def test_parsers_cover_every_index_url():
    assert set(PARSERS) == set(INDEX_URLS) == {"mhwilds", "mhrise", "mhworld"}


def test_index_urls_match_the_documented_pages():
    """三个地址就是 user 指定的列表页（带图标的那个）。"""
    assert INDEX_URLS["mhwilds"] == "https://mhwilds.kiranico.com/zh/data/monsters"
    assert INDEX_URLS["mhrise"] == "https://mhrise.kiranico.com/zh/data/monsters?view=lg"
    assert INDEX_URLS["mhworld"] == "https://mhworld.kiranico.com/zh/monsters"


def test_empty_html_yields_no_icons():
    for game in PARSERS:
        assert parse_icons(game, "") == {}
