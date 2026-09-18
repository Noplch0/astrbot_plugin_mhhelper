"""Monster-icon lookups for the three kiranico sites.

Every game's *listing* page carries one small icon per monster, but the three
sites share nothing: different markup, different hosts, different file naming,
and only mhwilds uses a CDN for detail pages. This module isolates that mess in
three pure functions — they take the listing page's HTML and return
``{monster_id: icon_url}``.

Why pure ``re`` and not BeautifulSoup: the scrapers run with httpx/bs4, but the
same rules also have to be usable from a plain-stdlib maintenance script (and
from the offline test suite). Keeping the parsing here means **one** definition
of "how to find an icon", so a site change is a one-line fix.

Pairing strategy: rather than guessing how many characters sit between an icon
and its monster link, each icon opens a *window* that ends where the next icon
begins, and the first monster link inside that window is that icon's monster.
Rows are icon-per-monster on all three sites, so this needs no magic offsets and
cannot drift across rows.

Id conventions differ per game and each matches ``data/monsters/<game>.json``:

* mhwilds — pinyin slug, e.g. ``ci-huo-long``, from ``/zh/data/monsters/<slug>``
* mhrise  — opaque numeric id, e.g. ``1301934382``, from ``/zh/data/monsters/<id>``
* mhworld — short code, e.g. ``wA8F8``, from ``/zh/monsters/<code>/<slug>``

All returned URLs are https: mhrise serves its icons over ``http://`` in the
markup, and a plain-http image inside the https-rendered t2i page would be
blocked as mixed content.
"""
from __future__ import annotations

import re
from typing import Iterable

#: Listing pages that carry the per-monster icons.
INDEX_URLS: dict[str, str] = {
    "mhwilds": "https://mhwilds.kiranico.com/zh/data/monsters",
    "mhrise": "https://mhrise.kiranico.com/zh/data/monsters?view=lg",
    "mhworld": "https://mhworld.kiranico.com/zh/monsters",
}

# --- icon patterns (one match per monster row) -----------------------------

# mhwilds: <img … src="https://mhwilds.kiranico.net/em_icon/EM0001_00_0.webp"/>
_MHWILDS_ICON = re.compile(r'src="(?P<icon>https://mhwilds\.kiranico\.net/em_icon/[\w.-]+\.webp)"')

# mhrise: <img src="http://cdn.kiranico.net/…/mhrise-web/images/icons/em132_05.png">
# Restricting the path to `images/icons/` keeps the site-cover images out.
_MHRISE_ICON = re.compile(
    r'src="(?P<icon>https?://cdn\.kiranico\.net/[^"]*?mhrise-web/images/icons/[\w.-]+\.png)"'
)

# mhworld: …/mhworld-web/mhw/icon/em105_ID.png (large) and ems061_01_ID.png (small).
# `ems?\d{3}` deliberately skips `ib_icon.png` (Iceborne badge) and
# `element_N.png` (elemental weakness chips), which are not portraits.
_MHWORLD_ICON = re.compile(
    r'src="(?P<icon>https://cdn\.kiranico\.net/[^"]*?mhworld-web/mhw/icon/ems?\d{3}(?:_\d{2})?_ID\.png)"'
)

# --- monster-link patterns -------------------------------------------------

_MHWILDS_LINK = re.compile(r'href="[^"]*?/data/monsters/(?P<id>[a-z0-9-]+)"')
# The language switcher points at `/data/monsters?view=lg` (no id), so requiring
# `/<digits>` afterwards excludes it.
_MHRISE_LINK = re.compile(r'href="[^"]*?/data/monsters/(?P<id>\d+)"')
_MHWORLD_LINK = re.compile(r'href="[^"]*?/monsters/(?P<id>[\w-]{4,12})/')


def _https(url: str) -> str:
    return url.replace("http://", "https://", 1) if url.startswith("http://") else url


def _pair_up(
    icons: Iterable[re.Match[str]], link_pattern: re.Pattern[str], html: str
) -> dict[str, str]:
    """Bind each icon to the first monster link that follows before the next icon."""
    ordered = list(icons)
    found: dict[str, str] = {}
    for index, match in enumerate(ordered):
        end = ordered[index + 1].start() if index + 1 < len(ordered) else len(html)
        link = link_pattern.search(html, match.end(), end)
        if link:
            found.setdefault(link.group("id"), _https(match.group("icon")))
    return found


def parse_mhwilds_icons(html: str) -> dict[str, str]:
    return _pair_up(_MHWILDS_ICON.finditer(html), _MHWILDS_LINK, html)


def parse_mhrise_icons(html: str) -> dict[str, str]:
    return _pair_up(_MHRISE_ICON.finditer(html), _MHRISE_LINK, html)


def parse_mhworld_icons(html: str) -> dict[str, str]:
    return _pair_up(_MHWORLD_ICON.finditer(html), _MHWORLD_LINK, html)


#: game → parser. Mirrors ``scraper.common.SCRAPERS``.
PARSERS: dict[str, object] = {
    "mhwilds": parse_mhwilds_icons,
    "mhrise": parse_mhrise_icons,
    "mhworld": parse_mhworld_icons,
}


def parse_icons(game: str, html: str) -> dict[str, str]:
    """Dispatch to the right parser; unknown games yield an empty map."""
    parser = PARSERS.get(game)
    return parser(html) if callable(parser) else {}  # type: ignore[operator]


__all__ = [
    "INDEX_URLS",
    "PARSERS",
    "parse_icons",
    "parse_mhrise_icons",
    "parse_mhwilds_icons",
    "parse_mhworld_icons",
]
