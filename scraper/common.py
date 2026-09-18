"""Per-game scraper implementations.

Each scraper class knows how to:
- fetch the index page
- extract monster/skill IDs and slugs
- fetch each detail page
- parse into a normalized dict matching core/schema
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Iterable

import httpx
from bs4 import BeautifulSoup

from .base import fetch, make_client
from .listing import monster_icons, monster_names, parse_skill_levels, skill_names
from .kiranico import (
    find_ailment_table,
    find_meat_table,
    get_meta,
    parse_ailment_table,
    parse_meat_table,
    parse_reward_table,
    section_rewards,
)

log = logging.getLogger("astrbot-mhhelper.scraper")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def _index_extras(game: str, text: str, kind: str) -> tuple[dict[str, str], dict[str, str]]:
    """列表页上能拿到的额外信息：怪物是「图标 + 中文名」，技能只有中文名。

    详情页没有图标，崛起/世界的详情页也没有中文名 —— 只能从列表页带过来，
    所以 ``list_monsters`` / ``list_skills`` 必须把这两个字段挂到 item 上，
    再由 run_update 写进数据。规则见 scraper/listing.py。
    """
    if kind == "monsters":
        return monster_icons(game, text), monster_names(game, text)
    return {}, skill_names(game, text)


# ----------------------------------------------------------------------
# mhwilds (Next.js, Chinese)
# ----------------------------------------------------------------------


class MHWildsScraper:
    BASE = "https://mhwilds.kiranico.com"
    LOCALE = "zh"
    #: 与 core.data_loader.GAMES 的键一致；scraper/icons.py 靠它选解析规则。
    GAME = "mhwilds"

    async def list_monsters(self, client: httpx.AsyncClient) -> list[dict[str, str]]:
        text = await fetch(client, f"{self.BASE}/{self.LOCALE}/data/monsters")
        return self._parse_index(text, "monsters")

    async def list_skills(self, client: httpx.AsyncClient) -> list[dict[str, str]]:
        text = await fetch(client, f"{self.BASE}/{self.LOCALE}/data/skills")
        return self._parse_index(text, "skills")

    def _parse_index(self, text: str, kind: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(text, "lxml")
        seen: set[str] = set()
        items: list[dict[str, str]] = []
        # 图标与中文名只在列表页上，随 item 传给 run_update。
        found_icons, found_names = _index_extras(self.GAME, text, kind)
        # Each monster link points to /zh/data/monsters/{slug}
        pattern = re.compile(rf"/{self.LOCALE}/data/{kind}/([a-z0-9-]+)")
        for a in soup.find_all("a", href=pattern):
            slug = pattern.search(a.get("href", "")).group(1)
            if slug in seen:
                continue
            seen.add(slug)
            label = a.get_text(strip=True)
            items.append({
                "id": slug,
                "name": label,
                "name_zh": found_names.get(slug, "") or label,
                "url": f"{self.BASE}/{self.LOCALE}/data/{kind}/{slug}",
                "icon": found_icons.get(slug, ""),
            })
        return items

    async def fetch_monster(self, client: httpx.AsyncClient, slug: str) -> dict[str, Any]:
        url = f"{self.BASE}/{self.LOCALE}/data/monsters/{slug}"
        text = await fetch(client, url)
        return self._parse_monster(text, slug)

    async def fetch_skill(self, client: httpx.AsyncClient, slug: str) -> dict[str, Any]:
        url = f"{self.BASE}/{self.LOCALE}/data/skills/{slug}"
        text = await fetch(client, url)
        return self._parse_skill(text, slug)

    # --- parsing -----------------------------------------------------

    def _parse_monster(self, text: str, slug: str) -> dict[str, Any]:
        soup = BeautifulSoup(text, "lxml")
        # Title (Chinese)
        h2 = soup.find("h2")
        name_zh = h2.get_text(strip=True) if h2 else slug
        # Find the english alias from the locale switcher / RSC payload
        # we approximate by extracting English text via mh-style
        meta = get_meta(soup)
        species = meta.get("种类") or meta.get("Species") or ""
        base_hp = self._parse_int(meta.get("基础HP") or meta.get("BaseHealth") or "")
        hr_point = self._parse_int(meta.get("HR 点数") or meta.get("HunterRankPoint") or "")
        meat_tbl = find_meat_table(soup)
        meat = parse_meat_table(meat_tbl) if meat_tbl else {"headers": [], "rows": []}
        ailment_tbl = find_ailment_table(soup)
        ailments = parse_ailment_table(ailment_tbl) if ailment_tbl else {}
        rewards = section_rewards(soup, ["素材", "剥取", "破坏", "目标", "报酬", "Reward"])
        return {
            "id": slug,
            "name_zh": name_zh,
            "name_en": "",  # filled later via name-en index if needed
            "aliases": [],
            "species": species,
            "hr_point": hr_point,
            "base_hp": base_hp,
            # 详情页没有图标，由 run_update 从列表页的 item["icon"] 填进来。
            "icon": "",
            "meat": meat,
            "ailments": ailments,
            "rewards": rewards,
        }

    def _parse_skill(self, text: str, slug: str) -> dict[str, Any]:
        soup = BeautifulSoup(text, "lxml")
        h2 = soup.find("h2")
        name_zh = h2.get_text(strip=True) if h2 else slug
        levels: list[dict[str, Any]] = []
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if not rows:
                continue
            for r in rows:
                cells = r.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                lv_raw = cells[0].get_text(strip=True)
                m = re.match(r"Lv\.?\s*(\d+)", lv_raw, re.IGNORECASE)
                if not m:
                    continue
                lv = int(m.group(1))
                effect = cells[-1].get_text(strip=True)
                levels.append({"lv": lv, "effect": effect})
            if levels:
                break
        return {
            "id": slug,
            "name_zh": name_zh,
            "name_en": "",
            "aliases": [],
            "levels": levels,
        }

    def _parse_int(self, raw: str) -> int | None:
        if not raw:
            return None
        digits = re.sub(r"[^\d-]", "", raw)
        try:
            return int(digits) if digits else None
        except ValueError:
            return None


# ----------------------------------------------------------------------
# mhrise (Laravel, English-only on this subdomain)
# ----------------------------------------------------------------------


class MHRiseScraper:
    BASE = "https://mhrise.kiranico.com"
    GAME = "mhrise"

    async def list_monsters(self, client: httpx.AsyncClient) -> list[dict[str, str]]:
        # 用 zh 列表页：图标和中文名都只在这里（详情页是英文的）。
        text = await fetch(client, f"{self.BASE}/zh/data/monsters?view=lg")
        return self._parse_monster_index(text)

    async def list_skills(self, client: httpx.AsyncClient) -> list[dict[str, str]]:
        text = await fetch(client, f"{self.BASE}/zh/data/skills")
        return self._parse_skill_index(text)

    def _parse_monster_index(self, text: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(text, "lxml")
        found_icons, found_names = _index_extras(self.GAME, text, "monsters")
        items: list[dict[str, str]] = []
        for a in soup.find_all("a", href=re.compile(r"/data/monsters/\d+")):
            href = a.get("href", "")
            mid = re.search(r"/data/monsters/(\d+)", href).group(1)
            items.append({
                "id": mid,
                "name": found_names.get(mid, ""),
                "name_zh": found_names.get(mid, ""),
                "url": f"{self.BASE}/data/monsters/{mid}",
                "icon": found_icons.get(mid, ""),
            })
        # Deduplicate by id
        seen = set()
        out = []
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            out.append(it)
        return out

    def _parse_skill_index(self, text: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(text, "lxml")
        _, found_names = _index_extras(self.GAME, text, "skills")
        items: list[dict[str, str]] = []
        for a in soup.find_all("a", href=re.compile(r"/data/skills/\d+")):
            href = a.get("href", "")
            sid = re.search(r"/data/skills/(\d+)", href).group(1)
            items.append({
                "id": sid,
                "name": found_names.get(sid, ""),
                "name_zh": found_names.get(sid, ""),
                "url": f"{self.BASE}/data/skills/{sid}",
            })
        seen = set()
        out = []
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            out.append(it)
        return out

    async def fetch_monster(self, client: httpx.AsyncClient, mid: str) -> dict[str, Any]:
        url = f"{self.BASE}/data/monsters/{mid}"
        text = await fetch(client, url)
        return self._parse_monster(text, mid)

    async def fetch_skill(self, client: httpx.AsyncClient, sid: str) -> dict[str, Any]:
        # zh 详情页：技能效果在那里的**中文**描述（/data/skills/<id> 是英文的）。
        url = f"{self.BASE}/zh/data/skills/{sid}"
        text = await fetch(client, url)
        return self._parse_skill(text, sid)

    def _parse_monster(self, text: str, mid: str) -> dict[str, Any]:
        soup = BeautifulSoup(text, "lxml")
        title = soup.title.get_text(strip=True) if soup.title else mid
        name_en = title.split("|")[0].strip()
        # First table on mhrise is the meat table; subsequent tables are ailments + rewards.
        tables = soup.find_all("table")
        meat = {"headers": [], "rows": []}
        ailments: dict[str, int] = {}
        rewards: dict[str, list[dict[str, Any]]] = {}
        if tables:
            # Locate meat table: first table with >= 5 numeric columns
            for t in tables:
                rows = t.find_all("tr")
                if len(rows) < 2:
                    continue
                parsed = self._try_parse_meat_rise(t)
                if parsed and parsed["rows"]:
                    meat = parsed
                    break
            # Ailments: table with header BuildUp
            for t in tables:
                if not t.find("tr"):
                    continue
                hdr = [c.get_text(strip=True) for c in t.find("tr").find_all(["th", "td"])]
                if "BuildUp" in hdr or "Buildup" in hdr:
                    ailments = parse_ailment_table(t)
                    break
            # Rewards: tables with at least 2 rows of {item, rate}
            for t in tables:
                items = parse_reward_table(t)
                if len(items) >= 2 and all("%" in str(it.get("rate", "")) for it in items[:2]):
                    # Try to find a heading from the previous h-tag
                    heading = self._previous_heading(t)
                    rewards[heading or "Reward"] = items
        return {
            "id": mid,
            "name_en": name_en,
            "name_zh": "",  # filled via alias file
            "aliases": [],
            "species": "",
            "hr_point": None,
            "base_hp": None,
            "icon": "",
            "meat": meat,
            "ailments": ailments,
            "rewards": rewards,
        }

    def _parse_skill(self, text: str, sid: str) -> dict[str, Any]:
        soup = BeautifulSoup(text, "lxml")
        title = soup.title.get_text(strip=True) if soup.title else sid
        name_en = title.split("|")[0].strip()
        # 整页交给解析器，它自己找第一段等级行（页面上还有装饰品表）。
        levels = parse_skill_levels(text)
        return {
            "id": sid,
            "name_en": name_en,
            "name_zh": "",
            "aliases": [],
            "levels": levels,
        }

    def _try_parse_meat_rise(self, table) -> dict[str, Any]:
        rows = table.find_all("tr")
        if len(rows) < 2:
            return None
        # Assume: part, state (optional "0"/"1"), 9 numbers
        parsed_rows: list[dict[str, Any]] = []
        for r in rows:
            cells = r.find_all(["td", "th"])
            texts = [c.get_text(strip=True) for c in cells]
            if not texts or not texts[0]:
                continue
            part = texts[0]
            rest = texts[1:]
            state = "通常"
            values: list[int] = []
            # Check for state token at position 0
            if rest and rest[0] in ("0", "1"):
                state = "通常" if rest[0] == "0" else "伤口"
                rest = rest[1:]
            for t in rest:
                try:
                    values.append(int(t.replace(",", "")))
                except ValueError:
                    continue
            parsed_rows.append({"part": part, "state": state, "values": values})
        headers = ["部位", "状态", "斩", "打", "弹", "火", "水", "雷", "冰", "龙", "麻"]
        return {"headers": headers, "rows": parsed_rows}

    def _previous_heading(self, table) -> str:
        prev = table.find_previous(["h2", "h3", "h4", "h5"])
        return prev.get_text(strip=True) if prev else ""


# ----------------------------------------------------------------------
# mhworld (English-only, MHWorld Iceborne)
# ----------------------------------------------------------------------


class MHWorldScraper:
    BASE = "https://mhworld.kiranico.com"
    GAME = "mhworld"

    async def list_monsters(self, client: httpx.AsyncClient) -> list[dict[str, str]]:
        # zh 列表页才带中文名与图标（详情页仍走 /en，那里有英文名与完整表格）。
        text = await fetch(client, f"{self.BASE}/zh/monsters")
        return self._parse_monster_index(text)

    async def list_skills(self, client: httpx.AsyncClient) -> list[dict[str, str]]:
        text = await fetch(client, f"{self.BASE}/zh/skilltrees")
        return self._parse_skill_index(text)

    def _parse_monster_index(self, text: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(text, "lxml")
        found_icons, found_names = _index_extras(self.GAME, text, "monsters")
        items: list[dict[str, str]] = []
        link = re.compile(r"/(?:en|zh)/monsters/([A-Za-z0-9]+)/([a-z0-9-]+)")
        for a in soup.find_all("a", href=link):
            m = link.search(a.get("href", ""))
            mid, slug = m.group(1), m.group(2)
            items.append({
                "id": mid,
                "slug": slug,
                "name": found_names.get(mid, ""),
                "name_zh": found_names.get(mid, ""),
                "url": f"{self.BASE}/en/monsters/{mid}/{slug}",
                "icon": found_icons.get(mid, ""),
            })
        seen = set()
        out = []
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            out.append(it)
        return out

    def _parse_skill_index(self, text: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(text, "lxml")
        _, found_names = _index_extras(self.GAME, text, "skills")
        items: list[dict[str, str]] = []
        link = re.compile(r"/(?:en|zh)/skilltrees/([A-Za-z0-9]+)/([a-z0-9-]+)")
        for a in soup.find_all("a", href=link):
            m = link.search(a.get("href", ""))
            sid, slug = m.group(1), m.group(2)
            items.append({
                "id": sid,
                "slug": slug,
                "name": found_names.get(sid, ""),
                "name_zh": found_names.get(sid, ""),
                "url": f"{self.BASE}/en/skilltrees/{sid}/{slug}",
            })
        seen = set()
        out = []
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            out.append(it)
        return out

    async def fetch_monster(self, client: httpx.AsyncClient, mid: str, slug: str = "") -> dict[str, Any]:
        # Need the slug to build the canonical URL; if we have an id-only path, fall back
        url = f"{self.BASE}/en/monsters/{mid}"
        if slug:
            url = f"{url}/{slug}"
        try:
            text = await fetch(client, url)
        except FileNotFoundError:
            text = await fetch(client, f"{self.BASE}/en/monsters/{mid}")
        return self._parse_monster(text, mid)

    async def fetch_skill(self, client: httpx.AsyncClient, sid: str, slug: str = "") -> dict[str, Any]:
        # zh 详情页才有中文效果，而且**必须带 slug**（`/zh/skilltrees/<id>` 单段是 404）。
        # slug 来自列表页；万一没拿到就退回英文页，宁可英文也别丢数据。
        if slug:
            try:
                text = await fetch(client, f"{self.BASE}/zh/skilltrees/{sid}/{slug}")
                return self._parse_skill(text, sid)
            except FileNotFoundError:
                log.warning("[mhworld] zh skill page missing for %s, falling back to en", sid)
        text = await fetch(client, f"{self.BASE}/en/skilltrees/{sid}")
        return self._parse_skill(text, sid)

    def _parse_monster(self, text: str, mid: str) -> dict[str, Any]:
        soup = BeautifulSoup(text, "lxml")
        title = soup.title.get_text(strip=True) if soup.title else mid
        name_en = title.split("-")[0].strip()
        tables = soup.find_all("table")
        # Meat table has headers [Part, Sever, Blunt, Ranged, Fire, Water, Thunder, Ice, Dragon, Stun, Stamina]
        meat = {"headers": [], "rows": []}
        ailments: dict[str, int] = {}
        rewards: dict[str, list[dict[str, Any]]] = {}
        for t in tables:
            hdr = self._table_headers(t)
            if hdr and hdr[0] == "Part" and "Sever" in hdr and "Blunt" in hdr:
                meat = self._parse_meat_world(t)
                break
        for t in tables:
            hdr = self._table_headers(t)
            if hdr and ("BuildUp" in hdr or "Buildup" in hdr):
                ailments = parse_ailment_table(t)
                break
        for t in tables:
            items = parse_reward_table(t)
            if len(items) >= 2:
                heading = self._previous_heading(t)
                rewards[heading or "Reward"] = items
        return {
            "id": mid,
            "name_en": name_en,
            "name_zh": "",
            "aliases": [],
            "species": "",
            "hr_point": None,
            "base_hp": None,
            "icon": "",
            "meat": meat,
            "ailments": ailments,
            "rewards": rewards,
        }

    def _parse_skill(self, text: str, sid: str) -> dict[str, Any]:
        soup = BeautifulSoup(text, "lxml")
        title = soup.title.get_text(strip=True) if soup.title else sid
        name_en = title.split("-")[0].strip()
        # 整页交给解析器，它自己找第一段等级行（页面上还有装饰品表）。
        levels = parse_skill_levels(text)
        return {
            "id": sid,
            "name_en": name_en,
            "name_zh": "",
            "aliases": [],
            "levels": levels,
        }

    def _table_headers(self, table) -> list[str]:
        if not table.find("tr"):
            return []
        return [c.get_text(strip=True) for c in table.find("tr").find_all(["th", "td"])]

    def _parse_meat_world(self, table) -> dict[str, Any]:
        rows = table.find_all("tr")
        parsed: list[dict[str, Any]] = []
        for r in rows[1:]:
            cells = r.find_all(["td", "th"])
            texts = [c.get_text(strip=True) for c in cells]
            if not texts or not texts[0]:
                continue
            part = texts[0]
            values: list[int] = []
            for t in texts[1:]:
                try:
                    values.append(int(t.replace(",", "")))
                except ValueError:
                    continue
            # Drop trailing stamina column (last 1 value if >9 numbers)
            # We want exactly 9: Sever, Blunt, Ranged, Fire, Water, Thunder, Ice, Dragon, Stun
            if len(values) > 9:
                values = values[:9]
            parsed.append({"part": part, "state": "通常", "values": values})
        return {
            "headers": ["部位", "状态", "斩", "打", "弹", "火", "水", "雷", "冰", "龙", "麻"],
            "rows": parsed,
        }

    def _previous_heading(self, table) -> str:
        prev = table.find_previous(["h2", "h3", "h4", "h5"])
        return prev.get_text(strip=True) if prev else ""


SCRAPERS: dict[str, Any] = {
    "mhwilds": MHWildsScraper,
    "mhrise": MHRiseScraper,
    "mhworld": MHWorldScraper,
}