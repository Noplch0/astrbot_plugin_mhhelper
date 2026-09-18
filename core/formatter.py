"""Plain-text formatter for monster/skill data.

Visual style: minimal / no box-drawing characters.

  - Skills       → vertical list (`Lv N  effect`) — most readable for prose
  - Meat tables  → header row + aligned data rows, no borders
  - List shapes  → bullets, simple alignment
  - Errors       → plain text + bulleted suggestions

All output uses spaces for alignment; CJK width is handled via wcwidth.
For IM clients that preserve monospace blocks (most of them) the result is
neat; for clients that don't, the plain text still reads cleanly without
the heavy `+---+` ASCII borders.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Iterable, Sequence

from .data_loader import GAME_LABELS

# ----------------------------------------------------------------------
# CJK-aware width helpers
# ----------------------------------------------------------------------
try:
    from wcwidth import wcswidth as _wcswidth  # type: ignore
except Exception:  # pragma: no cover

    def _wcswidth(s: str) -> int:
        width = 0
        for ch in s:
            if unicodedata.east_asian_width(ch) in ("W", "F"):
                width += 2
            elif ch == "\t":
                width += 4
            else:
                width += 1
        return width


def _pad(text: str, width: int, align: str = "left") -> str:
    current = _wcswidth(text) if text else 0
    fill = max(width - current, 0)
    if align == "right":
        return " " * fill + text
    if align == "center":
        return " " * (fill // 2) + text + " " * (fill - fill // 2)
    return text + " " * fill


# ----------------------------------------------------------------------
# Light table — header row + aligned data, no borders / separators.
# This is the only "table" we emit; numeric columns are right-aligned
# when their header looks numeric.
# ----------------------------------------------------------------------

_NUMERIC_HINTS = ("数", "伤害", "HP", "Lv", "等级", "BuildUp", "Decay", "概率", "率", "点数")


def _align_for(header: str) -> str:
    return "right" if any(k in header for k in _NUMERIC_HINTS) else "left"


def _light_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Render a header row + data rows separated by a single blank line.

    No borders, no separators between rows — just whitespace alignment.
    """
    rows = [list(r) for r in rows]
    if not rows:
        return "  ".join(str(h) for h in headers)
    widths: list[int] = []
    for i, h in enumerate(headers):
        col_vals = [h] + [r[i] if i < len(r) else "" for r in rows]
        widths.append(max(_wcswidth(str(v)) if v else 0 for v in col_vals))
    aligns = [_align_for(h) for h in headers]

    def _fmt_row(values: Sequence[Any]) -> str:
        cells = []
        for i, v in enumerate(values):
            val = "" if v is None else str(v)
            cells.append(_pad(val, widths[i], aligns[i]))
        return "  ".join(cells)

    header_line = _fmt_row(headers)
    out = [header_line]
    out.extend(_fmt_row(r) for r in rows)
    return "\n".join(out)


# ----------------------------------------------------------------------
# Renderers
# ----------------------------------------------------------------------


def render_help() -> str:
    return (
        "🎮 怪物猎人查询\n"
        "\n"
        "全部查询都收在 /mh 指令组下,格式: /mh <子命令> [名字] [作品]\n"
        "\n"
        "怪物\n"
        "  /mh 怪物列表 [作品]      列出该作大型怪物\n"
        "  /mh 怪物 <名字> [作品]   怪物基础信息(种类 / HR 点数 / HP)\n"
        "  /mh 肉质 <名字> [作品]   肉质表(斩 / 打 / 弹 / 属性)\n"
        "  /mh 弱点 <名字> [作品]   属性弱点与状态异常累积\n"
        "  /mh 素材 <名字> [作品]   剥取 / 破坏 / 目标报酬\n"
        "\n"
        "技能\n"
        "  /mh 技能列表 [作品]      列出该作技能\n"
        "  /mh 技能 <名字> [作品]   技能各等级效果\n"
        "\n"
        "其他\n"
        "  /mh 作品                列出已启用的作品\n"
        "  /mh 更新 [作品]          管理员: 在线刷新数据\n"
        "  /mh 帮助                显示本帮助\n"
        "\n"
        "作品标识(可省略,省略时按「上次使用 → 默认作品」)\n"
        "  mhworld / world / 世界 / iceborne    怪物猎人:世界\n"
        "  mhrise  / rise  / 崛起 / sunbreak    怪物猎人:崛起\n"
        "  mhwilds / wilds / 荒野               怪物猎人:荒野\n"
        "\n"
        "子命令支持英文别名: meat / weak / rewards / monster / monsters /\n"
        "skill / skills / games / update / help\n"
        "\n"
        "示例\n"
        "  /mh 肉质 火龙\n"
        "  /mh meat Rathian 荒野\n"
        "  /mh 技能列表 mhrise\n"
    )


def render_games(games: Sequence[str]) -> str:
    lines = ["已启用的作品:"]
    for g in games:
        lines.append(f"  • {g}  ({GAME_LABELS.get(g, g)})")
    return "\n".join(lines)


def render_monster_list(game: str, monsters: Sequence[dict[str, Any]], max_rows: int = 30) -> str:
    total = len(monsters)
    truncated = monsters[:max_rows]
    lines = [f"📜 {GAME_LABELS.get(game, game)} — 大型怪物 ({total})", ""]
    for m in truncated:
        zh = m.get("name_zh") or m.get("id") or "?"
        en = m.get("name_en") or ""
        if en and en != zh:
            lines.append(f"  • {zh} ({en})")
        else:
            lines.append(f"  • {zh}")
    extra = ""
    if total > max_rows:
        extra = f"\n… 共 {total} 条,本条消息仅展示前 {max_rows} 条。请用具体名字查询。"
    return "\n".join(lines) + extra


def render_skill_list(game: str, skills: Sequence[dict[str, Any]], max_rows: int = 30) -> str:
    total = len(skills)
    truncated = skills[:max_rows]
    lines = [f"📜 {GAME_LABELS.get(game, game)} — 技能 ({total})", ""]
    for s in truncated:
        zh = s.get("name_zh") or s.get("id") or "?"
        en = s.get("name_en") or ""
        lv = len(s.get("levels") or [])
        if en and en != zh:
            lines.append(f"  • {zh} ({en})  — {lv} 级")
        else:
            lines.append(f"  • {zh}  — {lv} 级")
    extra = ""
    if total > max_rows:
        extra = f"\n… 共 {total} 条,本条消息仅展示前 {max_rows} 条。"
    return "\n".join(lines) + extra


def render_monster_info(monster: dict[str, Any], game: str) -> str:
    name_zh = monster.get("name_zh") or monster.get("id")
    name_en = monster.get("name_en") or ""
    lines = [f"🐉 {name_zh}" + (f" ({name_en})" if name_en and name_en != name_zh else "")]
    lines.append(f"  作品: {GAME_LABELS.get(game, game)}")
    if monster.get("species"):
        lines.append(f"  种类: {monster['species']}")
    if monster.get("hr_point") is not None:
        lines.append(f"  HR 点数: {monster['hr_point']}")
    if monster.get("base_hp") is not None:
        lines.append(f"  基础 HP: {monster['base_hp']}")
    if monster.get("aliases"):
        lines.append(f"  别名: {', '.join(monster['aliases'])}")
    if monster.get("id"):
        lines.append(f"  ID: {monster['id']}")
    return "\n".join(lines)


def render_meat(monster: dict[str, Any], game: str, max_rows: int = 30) -> str:
    name_zh = monster.get("name_zh") or monster.get("id")
    name_en = monster.get("name_en") or ""
    meat = monster.get("meat") or {}
    headers: list[str] = list(meat.get("headers") or [])
    rows_raw: list[dict[str, Any]] = list(meat.get("rows") or [])
    if not headers:
        return f"🍖 {name_zh} — 该作品暂无肉质数据"

    has_part = any(h in ("部位", "Part") for h in headers)
    has_state = any(h in ("状态", "State") for h in headers)

    truncated = rows_raw[:max_rows]
    body_rows: list[list[str]] = []
    for r in truncated:
        cells: list[str] = []
        if has_part:
            cells.append(str(r.get("part") or ""))
        if has_state:
            cells.append(str(r.get("state") or "通常"))
        for v in r.get("values") or []:
            cells.append(str(v))
        while len(cells) < len(headers):
            cells.append("?")
        body_rows.append(cells[: len(headers)])

    table = _light_table(headers, body_rows)
    extra = ""
    if len(rows_raw) > max_rows:
        extra = f"\n… 共 {len(rows_raw)} 行,本条消息仅展示前 {max_rows} 行。"
    title = f"🍖 {name_zh}" + (f" ({name_en})" if name_en and name_en != name_zh else "") + " — 肉质表"
    return title + "\n\n" + table + extra


def render_weak(monster: dict[str, Any], game: str) -> str:
    name_zh = monster.get("name_zh") or monster.get("id")
    name_en = monster.get("name_en") or ""
    title = "⚔️ " + name_zh + (f" ({name_en})" if name_en and name_en != name_zh else "")
    lines = [title]
    ailments = monster.get("ailments") or {}
    if ailments:
        lines.append("")
        lines.append("状态异常累积值:")
        for k, v in ailments.items():
            lines.append(f"  • {k}: {v}")
    else:
        lines.append("该作品暂无状态异常数据。")
    # Best attribute values summary
    meat = monster.get("meat") or {}
    headers = list(meat.get("headers") or [])
    rows_raw = list(meat.get("rows") or [])
    if headers and rows_raw:
        attr_indices: list[tuple[str, int]] = []
        for i, h in enumerate(headers):
            if h in ("火", "水", "雷", "冰", "龙", "麻"):
                attr_indices.append((h, i - 2))
        best: list[tuple[str, int]] = []
        for attr, idx in attr_indices:
            vals = []
            for r in rows_raw:
                v = (r.get("values") or [0] * (idx + 1))
                if 0 <= idx < len(v):
                    vals.append(int(v[idx] or 0))
            if vals:
                best.append((attr, max(vals)))
        if best:
            lines.append("")
            lines.append("属性弱点概览 (各部位最大值):")
            for attr, v in best:
                lines.append(f"  • {attr}: {v}")
    return "\n".join(lines)


def render_rewards(monster: dict[str, Any], game: str, max_rows: int = 30) -> str:
    name_zh = monster.get("name_zh") or monster.get("id")
    name_en = monster.get("name_en") or ""
    rewards = monster.get("rewards") or {}
    if not rewards:
        return f"💎 {name_zh} — 该作品暂无报酬数据"
    title = "💎 " + name_zh + (f" ({name_en})" if name_en and name_en != name_zh else "") + " — 素材报酬"
    lines = [title]
    for category, items in rewards.items():
        lines.append("")
        lines.append(f"▸ {category}")
        if not items:
            lines.append("  (无数据)")
            continue
        truncated = items[:max_rows]
        for it in truncated:
            if isinstance(it, dict):
                item = str(it.get("item") or "?")
                rate = str(it.get("rate") or "")
                if rate:
                    lines.append(f"  • {item}  —  {rate}")
                else:
                    lines.append(f"  • {item}")
            else:
                lines.append(f"  • {it}")
        if len(items) > max_rows:
            lines.append(f"  … 共 {len(items)} 条,本条消息仅展示前 {max_rows} 条。")
    return "\n".join(lines)


def render_skill(skill: dict[str, Any], game: str) -> str:
    name_zh = skill.get("name_zh") or skill.get("id")
    name_en = skill.get("name_en") or ""
    levels = skill.get("levels") or []
    title = "📘 " + name_zh + (f" ({name_en})" if name_en and name_en != name_zh else "") + " — " + GAME_LABELS.get(game, game)
    lines = [title]
    if not levels:
        lines.append("该作品暂无技能效果数据。")
        return "\n".join(lines)
    lines.append("")
    for lv in levels:
        if isinstance(lv, dict):
            lv_str = str(lv.get("lv") or "?")
            effect = str(lv.get("effect") or "?").strip()
            lines.append(f"Lv {lv_str}  {effect}")
        else:
            lines.append(f"?  {lv}")
    return "\n".join(lines)


def render_error(title: str, detail: str, suggestions: list[str] | None = None) -> str:
    msg = f"⚠️ {title}\n{detail}"
    if suggestions:
        msg += "\n\n你可能想查:\n" + "\n".join(f"  • {s}" for s in suggestions)
    return msg


def render_update_result(game: str, monsters: int, skills: int, seconds: float) -> str:
    return (
        f"✅ 已更新 {GAME_LABELS.get(game, game)}\n"
        f"  怪物: {monsters} 条\n"
        f"  技能: {skills} 条\n"
        f"  耗时: {seconds:.1f}s"
    )