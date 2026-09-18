"""Kiranico HTML → unified schema parser.

Shared parsing helpers (table parsing, reward parsing) reused by all three
game-specific scrapers.
"""
from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

# Map of icon file basename → unified column name.
ICON_TO_HEADER: dict[str, str] = {
    "hit_slash.png": "斩",
    "hit_strike.png": "打",
    "hit_shell.png": "弹",
    "element_fire.png": "火",
    "element_water.png": "水",
    "element_thunder.png": "雷",
    "element_ice.png": "冰",
    "element_dragon.png": "龙",
    "element_stun.png": "麻",
}

# English column header → unified name (fallback for mhworld / mhrise).
EN_TO_HEADER: dict[str, str] = {
    "Sever": "斩",
    "Blunt": "打",
    "Ranged": "弹",
    "Shot": "弹",
    "Fire": "火",
    "Water": "水",
    "Thunder": "雷",
    "Ice": "冰",
    "Dragon": "龙",
    "Stun": "麻",
}

DEFAULT_STATE = "通常"


def _img_basename(src: str) -> str:
    return src.split("/")[-1] if src else ""


def detect_headers_from_row(row: Tag) -> tuple[list[str], int]:
    """Return (headers, num_value_cols) for a header row.

    Returns headers as: ["部位", "状态", <value-col-1>, ...] where the value
    columns are named after the icon src or recognized English text.
    Empty cells (no img and no text) are skipped so positions align with
    numeric data columns.
    """
    headers: list[str] = []
    num_value = 0
    for cell in row.find_all(["th", "td"]):
        text = cell.get_text(strip=True)
        img = cell.find("img")
        if img is not None:
            base = _img_basename(img.get("src") or "")
            label = ICON_TO_HEADER.get(base, "")
            if label:
                headers.append(label)
                num_value += 1
            continue
        if text in EN_TO_HEADER:
            headers.append(EN_TO_HEADER[text])
            num_value += 1
            continue
        if text in ("Part", "部位", "部位名"):
            headers.insert(0, "部位")
            continue
        if text in ("State", "状態", "状态"):
            headers.insert(1 if headers and headers[0] == "部位" else 0, "状态")
            continue
        # Skip empty / unrecognised cells — they don't add to header count.
    if "部位" not in headers:
        headers = ["部位"] + headers
    if "状态" not in headers and num_value >= 4:
        headers = headers[:1] + ["状态"] + headers[1:]
    return headers, num_value


def parse_meat_table(table: Tag) -> dict[str, Any] | None:
    """Parse a meat (hitzone) table. Return None if structure is unrecognised."""
    rows = table.find_all("tr")
    if len(rows) < 2:
        return None

    headers, num_value = detect_headers_from_row(rows[0])
    if not headers or num_value < 4:
        return None

    # Ensure headers start with 部位 [+ 状态]
    if "部位" not in headers:
        headers = ["部位"] + headers
    if "状态" not in headers:
        # Insert state column after 部位
        idx = headers.index("部位") + 1
        headers = headers[:idx] + ["状态"] + headers[idx:]

    parsed_rows: list[dict[str, Any]] = []
    for r in rows[1:]:
        cells = r.find_all(["td", "th"])
        texts = [c.get_text(strip=True) for c in cells]
        if not texts:
            continue
        part = texts[0] if len(texts) > 0 else ""
        # state either from column 1 or implicit
        if "状态" in headers:
            state_idx = headers.index("状态")
            state = texts[state_idx] if state_idx < len(texts) and texts[state_idx] else DEFAULT_STATE
            if not state:
                state = DEFAULT_STATE
            # numeric values: skip part & state columns
            value_start = max(state_idx + 1, 1)
        else:
            state = DEFAULT_STATE
            value_start = 1
        values: list[int] = []
        for raw in texts[value_start:]:
            if raw == "":
                continue
            try:
                values.append(int(raw.replace(",", "")))
            except ValueError:
                # Drop non-numeric columns (e.g., Stamina in mhworld)
                continue
        if not part and not values:
            continue
        parsed_rows.append({"part": part or "?", "state": state, "values": values})

    if not parsed_rows:
        return None
    return {"headers": headers, "rows": parsed_rows}


def parse_ailment_table(table: Tag) -> dict[str, int]:
    """Parse a status-ailment BuildUp/Damage/Decay table. Return mapping."""
    out: dict[str, int] = {}
    rows = table.find_all("tr")
    if len(rows) < 2:
        return out
    headers = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    # Build column index map
    name_col = 0
    buildup_col = None
    for i, h in enumerate(headers):
        if h in ("BuildUp", "Buildup", "累积", "积蓄"):
            buildup_col = i
            break
    if buildup_col is None:
        # try second column
        buildup_col = 1 if len(headers) > 1 else 0
    for r in rows[1:]:
        cells = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
        if not cells:
            continue
        name = cells[name_col]
        if not name:
            continue
        raw = cells[buildup_col] if buildup_col < len(cells) else ""
        # extract first number (e.g., "250 (+150) → 700" → 250)
        m = re.search(r"-?\d+", raw)
        if m:
            out[name] = int(m.group(0))
    return out


def parse_reward_blocks(soup: BeautifulSoup) -> dict[str, list[dict[str, Any]]]:
    """For mhwilds: parse rewards grouped by section headers.

    Each block is preceded by a heading like '上位素材', '下位素材', etc.
    For mhrise / mhworld the per-table structure already gives categories.
    """
    return {}


def parse_reward_table(table: Tag) -> list[dict[str, Any]]:
    """Parse a single reward table: list of {item, rate}."""
    items: list[dict[str, Any]] = []
    rows = table.find_all("tr")
    if len(rows) < 1:
        return items
    # First row may be the category header (mhworld) or items
    for r in rows:
        cells = r.find_all(["td", "th"])
        texts = [c.get_text(strip=True) for c in cells]
        if len(texts) < 2:
            continue
        # Pattern A: item | rate  (mhworld)
        # Pattern B: item | source | rate (mhrise)
        if len(texts) == 2:
            item, rate = texts
            source = ""
        else:
            item = texts[0]
            # Look for last numeric-looking token as rate
            rate = ""
            source = texts[1] if len(texts) > 2 else ""
            for t in reversed(texts):
                if re.search(r"\d+%", t):
                    rate = t
                    break
            if not rate:
                rate = texts[-1]
        items.append({"item": item, "source": source, "rate": rate})
    return items


def find_meat_table(soup: BeautifulSoup) -> Tag | None:
    """Locate the meat/hitzone table within a monster page."""
    for table in soup.find_all("table"):
        headers, num_value = detect_meat_headers(table)
        if num_value >= 4:
            return table
    return None


def detect_meat_headers(table: Tag) -> tuple[list[str], int]:
    """Robust detection of meat table headers."""
    rows = table.find_all("tr")
    if not rows:
        return [], 0
    return detect_headers_from_row(rows[0])


def find_ailment_table(soup: BeautifulSoup) -> Tag | None:
    for table in soup.find_all("table"):
        headers = [c.get_text(strip=True) for c in table.find_all("tr")[0].find_all(["th", "td"])] if table.find("tr") else []
        if "BuildUp" in headers or "Buildup" in headers:
            return table
    return None


def get_meta(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract Species / BaseHealth / HunterRankPoint from the basic-info table."""
    out: dict[str, Any] = {}
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) != 3:
            continue
        keys = [r.find_all(["td", "th"])[0].get_text(strip=True) for r in rows if r.find_all(["td", "th"])]
        if "Species" in keys or "种类" in keys:
            for r in rows:
                cells = r.find_all(["td", "th"])
                if len(cells) >= 2:
                    k = cells[0].get_text(strip=True)
                    v = cells[1].get_text(strip=True)
                    out[k] = v
            break
    return out


def section_rewards(soup: BeautifulSoup, headings: list[str]) -> dict[str, list[dict[str, Any]]]:
    """For mhwilds-style pages: walk <section> blocks and parse each reward block.

    Each <section> contains an <h4> heading and a <table> of items.
    Falls back to grouping rows of the trailing reward table by their
    in-row category column (剥取 / 部位破坏报酬 / 目标报酬 ...).
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for section in soup.find_all("section"):
        h = section.find(["h2", "h3", "h4"])
        if not h:
            continue
        title = h.get_text(strip=True)
        if any(kw in title for kw in headings):
            table = section.find("table")
            if table:
                out[title] = parse_reward_table(table)
    if out:
        return out
    # Fallback: group a single reward table by category column
    for table in soup.find_all("table"):
        text = table.get_text()
        if not any(kw in text for kw in ("剥取", "報酬", "報酬", "破坏", "報酬", "素材")):
            continue
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        grouped: dict[str, list[dict[str, Any]]] = {}
        last_cat = "其他"
        # Infer column layout from the first row that has 2+ cells
        item_idx = 0
        cat_idx = 1
        rate_idx = 2
        for r in rows:
            cells = r.find_all(["td", "th"])
            texts = [c.get_text(strip=True) for c in cells]
            if not texts:
                continue
            item = texts[item_idx] if len(texts) > item_idx else ""
            cat = texts[cat_idx] if len(texts) > cat_idx else ""
            rate = texts[rate_idx] if len(texts) > rate_idx else ""
            if cat:
                last_cat = cat
            else:
                cat = last_cat
            grouped.setdefault(cat or "其他", []).append({"item": item, "source": "", "rate": rate})
        if grouped:
            # Filter out empty category buckets
            return {k: v for k, v in grouped.items() if any(it["item"] for it in v)}
    return out