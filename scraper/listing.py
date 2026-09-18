"""Pure-regex parsing rules for kiranico pages.

Covers two kinds of page:

* **listing pages** — monster icons and Chinese names (and skill Chinese names);
* **skill detail pages** — the per-level effect text.

Why pure ``re`` and not BeautifulSoup: the scrapers run with httpx/bs4, but these
same rules also have to be usable from plain-stdlib maintenance scripts and from
the offline test suite — and ``scraper/kiranico.py`` imports bs4 at module level,
so anything living there is unreachable without it. Keeping the rules here means
**one** definition per page, so a site change is a one-line fix.

The three sites share nothing — different markup, hosts, file naming and id
conventions — but every listing page is keyed by the same id that appears in
``data/monsters/<game>.json`` and ``data/skills/<game>.json``, so the plugin can
enrich its data offline and then never touch the network at query time.

What lives where (verified against the live pages):

| page | url | id | icon | 中文名 |
|---|---|---|---|---|
| mhwilds monsters | `/zh/data/monsters` | pinyin slug | `em_icon/EM0001_00_0.webp` | anchor text |
| mhrise monsters | `/zh/data/monsters?view=lg` | numeric | `images/icons/em132_05.png` | img `alt` |
| mhworld monsters | `/zh/monsters` | 5-char code | `icon/em105_ID.png` | anchor text |
| mhrise skills | `/zh/data/skills` | numeric | — | anchor 的内层文本 |
| mhworld skills | `/zh/skilltrees` | 5-char code | — | anchor text |

Why pure ``re`` and not BeautifulSoup: the scrapers run with httpx/bs4, but the
same rules also have to be usable from a plain-stdlib maintenance script and from
the offline test suite. Keeping them here means **one** definition per page, so a
site change is a one-line fix.

Pairing strategy: each icon opens a *window* that ends where the next icon
begins, and the first monster link inside that window belongs to that icon. Rows
are icon-per-monster everywhere, so this needs no magic character offsets and
cannot drift across rows (an earlier fixed-width window silently missed 24
MHWorld monsters).

All icon URLs are https: mhrise serves its icons over ``http://`` in the markup,
and a plain-http image inside the https-rendered t2i card would be blocked as
mixed content.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Iterator

#: Monster listing pages (they carry both the icon and the 中文名).
MONSTER_INDEX_URLS: dict[str, str] = {
    "mhwilds": "https://mhwilds.kiranico.com/zh/data/monsters",
    "mhrise": "https://mhrise.kiranico.com/zh/data/monsters?view=lg",
    "mhworld": "https://mhworld.kiranico.com/zh/monsters",
}

#: Skill listing pages (only the 中文名; skills have no icon).
SKILL_INDEX_URLS: dict[str, str] = {
    "mhrise": "https://mhrise.kiranico.com/zh/data/skills",
    "mhworld": "https://mhworld.kiranico.com/zh/skilltrees",
}

_TAG = re.compile(r"<[^>]+>")


def _text(raw: str) -> str:
    """Strip tags/whitespace from an anchor's inner HTML."""
    return re.sub(r"\s+", " ", _TAG.sub(" ", raw)).strip()


def _https(url: str) -> str:
    return url.replace("http://", "https://", 1) if url.startswith("http://") else url


# --------------------------------------------------------------------------
# mhwilds — 图标在 <img src="…/em_icon/EM0001_00_0.webp">，名字在紧随的锚文本里
# --------------------------------------------------------------------------

_MHWILDS_ICON = re.compile(
    r'src="(?P<icon>https://mhwilds\.kiranico\.net/em_icon/[\w.-]+\.webp)"'
)
# 名字可能直接是锚文本，也可能包在 <span> 等内层标签里，所以统一取 `</a>` 之前的
# 整段内层 HTML 再剥标签（荒野就是 `<a …><span>雌火龙</span></a>`）。
_MHWILDS_MONSTER_LINK = re.compile(
    r'href="[^"]*?/data/monsters/(?P<id>[a-z0-9-]+)"[^>]*>(?P<name>.*?)</a>', re.S
)


# --------------------------------------------------------------------------
# mhrise — 图标与名字在同一个 <img> 上（名字是 alt），id 在紧随的链接里
# --------------------------------------------------------------------------

_MHRISE_ICON = re.compile(
    r'src="(?P<icon>https?://cdn\.kiranico\.net/[^"]*?mhrise-web/images/icons/[\w.-]+\.png)"'
    r'[^>]*?alt="(?P<name>[^"]{1,40})"'
)
# 语言切换链接是 `/data/monsters?view=lg`（没有 id），要求 `/<数字>` 就不会误配。
_MHRISE_MONSTER_LINK = re.compile(r'href="[^"]*?/data/monsters/(?P<id>\d+)"')
_MHRISE_SKILL_LINK = re.compile(
    r'href="[^"]*?/data/skills/(?P<id>\d+)"[^>]*>(?P<name>.*?)</a>', re.S
)


# --------------------------------------------------------------------------
# mhworld — 图标与名字分别在 <img> 和紧随的锚文本里
# --------------------------------------------------------------------------

# `ems?\d{3}` 有意排除 `ib_icon.png`（冰原徽标）与 `element_N.png`（属性图标）。
_MHWORLD_ICON = re.compile(
    r'src="(?P<icon>https://cdn\.kiranico\.net/[^"]*?mhworld-web/mhw/icon/'
    r'ems?\d{3}(?:_\d{2})?_ID\.png)"'
)
_MHWORLD_MONSTER_LINK = re.compile(
    r'href="[^"]*?/monsters/(?P<id>[\w-]{4,12})/[^"]*"[^>]*>(?P<name>.*?)</a>', re.S
)
_MHWORLD_SKILL_LINK = re.compile(
    r'href="[^"]*?/skilltrees/(?P<id>[\w-]{4,12})/[^"]*"[^>]*>(?P<name>.*?)</a>', re.S
)


def _windows(matches: list[re.Match[str]], html: str) -> Iterator[tuple[re.Match[str], str]]:
    """每一处图标开一个窗口，到下一处图标为止。"""
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        yield match, html[match.end():end]


def _pair(icon_matches: Iterable[re.Match[str]], link: re.Pattern[str], html: str) -> dict[str, dict[str, str]]:
    """把每处图标和它窗口里的第一个怪物链接配起来。

    名字有两种来源，取到哪个用哪个：崛起在 ``<img alt>`` 上，荒野/世界在锚文本里。
    """
    ordered = list(icon_matches)
    found: dict[str, dict[str, str]] = {}
    for match, window in _windows(ordered, html):
        hit = link.search(window)
        if not hit:
            continue
        entry = found.setdefault(
            hit.group("id"),
            {"icon": _https(match.group("icon")), "name": ""},
        )
        name = _text(match.groupdict().get("name") or "") or _text(
            hit.groupdict().get("name") or ""
        )
        if name and not entry["name"]:
            entry["name"] = name
    return found


# --------------------------------------------------------------------------
# 站点解析器 —— 统一返回 {id: {"icon": url, "name": 中文名}}（没有的字段为空串）
# --------------------------------------------------------------------------


def parse_mhwilds_monsters(html: str) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for match, window in _windows(list(_MHWILDS_ICON.finditer(html)), html):
        hit = _MHWILDS_MONSTER_LINK.search(window)
        if not hit:
            continue
        found.setdefault(
            hit.group("id"),
            {"icon": _https(match.group("icon")), "name": _text(hit.group("name"))},
        )
    return found


def parse_mhrise_monsters(html: str) -> dict[str, dict[str, str]]:
    return _pair(_MHRISE_ICON.finditer(html), _MHRISE_MONSTER_LINK, html)


def parse_mhworld_monsters(html: str) -> dict[str, dict[str, str]]:
    return _pair(_MHWORLD_ICON.finditer(html), _MHWORLD_MONSTER_LINK, html)


def _parse_anchors(link: re.Pattern[str], html: str) -> dict[str, str]:
    """从锚点里取 {id: 名字}（名字可能嵌在多层标签里）。"""
    out: dict[str, str] = {}
    for hit in link.finditer(html):
        name = _text(hit.group("name"))
        if name and hit.group("id") not in out:
            out[hit.group("id")] = name
    return out


def parse_mhrise_skills(html: str) -> dict[str, str]:
    return _parse_anchors(_MHRISE_SKILL_LINK, html)


def parse_mhworld_skills(html: str) -> dict[str, str]:
    return _parse_anchors(_MHWORLD_SKILL_LINK, html)


#: game → 怪物列表页解析器。
MONSTER_PARSERS: dict[str, Any] = {
    "mhwilds": parse_mhwilds_monsters,
    "mhrise": parse_mhrise_monsters,
    "mhworld": parse_mhworld_monsters,
}

#: game → 技能列表页解析器。
SKILL_PARSERS: dict[str, Any] = {
    "mhrise": parse_mhrise_skills,
    "mhworld": parse_mhworld_skills,
}


def parse_monsters(game: str, html: str) -> dict[str, dict[str, str]]:
    parser = MONSTER_PARSERS.get(game)
    return parser(html) if callable(parser) else {}


def monster_icons(game: str, html: str) -> dict[str, str]:
    """{id: 图标 url}，只保留有图标的。"""
    return {k: v["icon"] for k, v in parse_monsters(game, html).items() if v.get("icon")}


def monster_names(game: str, html: str) -> dict[str, str]:
    """{id: 中文名}，只保留有名字的。"""
    return {k: v["name"] for k, v in parse_monsters(game, html).items() if v.get("name")}


def skill_names(game: str, html: str) -> dict[str, str]:
    parser = SKILL_PARSERS.get(game)
    return parser(html) if callable(parser) else {}




# --------------------------------------------------------------------------
# 技能详情页：等级 → 效果
# --------------------------------------------------------------------------

_LEVEL = re.compile(r"(?:Lv\.?|等级)\s*(\d+)", re.IGNORECASE)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)


def parse_skill_levels(html: str) -> list[dict[str, str]]:
    """从技能详情页 HTML 里取 ``[{lv, effect}]``。

    两个子域的表结构都是 **等级 | 效果 | (数值参数…)**：:

        mhrise   <td>Lv1</td><td>攻击力+3</td>
        mhworld  <td>等级1</td><td><strong>减少…</strong></td><td><code>200</code>…

    所以**效果永远是第 2 列**。旧代码取 ``cells[-1]``，在世界那儿取到的是
    ``<code>`` 参数列 —— 那边每个技能的效果都变成了 ``"0"``。

    只取**第一段连续**的等级行：同一页面后面还有装饰品 / 道具表，它们的首列不是
    等级，正好被跳过。等级行的效果为空时保留空串 —— kiranico 自己就是空的
    （例：抑制偏移 Lv3）。
    """
    levels: list[dict[str, str]] = []
    for row in _ROW.finditer(html):
        cells = [_text(cell) for cell in _CELL.findall(row.group(1))]
        if len(cells) < 2:
            continue
        match = _LEVEL.search(cells[0])
        if not match:
            if levels:  # 第一段等级行结束
                break
            continue
        levels.append({"lv": int(match.group(1)), "effect": cells[1]})
    return levels


__all__ = [
    "MONSTER_INDEX_URLS",
    "MONSTER_PARSERS",
    "SKILL_INDEX_URLS",
    "SKILL_PARSERS",
    "monster_icons",
    "monster_names",
    "parse_mhrise_monsters",
    "parse_mhrise_skills",
    "parse_mhwilds_monsters",
    "parse_mhworld_monsters",
    "parse_mhworld_skills",
    "parse_monsters",
    "parse_skill_levels",
    "skill_names",
]
