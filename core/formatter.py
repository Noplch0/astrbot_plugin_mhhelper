"""Plain-text formatter for monster/skill data.

Generates ASCII-aligned tables suitable for any IM (Markdown tables do not
render in many chat platforms, so we use raw text).
"""
from __future__ import annotations

import unicodedata
from typing import Any, Iterable, Sequence

from .data_loader import GAME_LABELS

# Display width for fixed CJK chars (Half/Full width aware).
try:
    from wcwidth import wcswidth as _wcswidth  # type: ignore
except Exception:  # pragma: no cover - fallback when wcwidth not installed

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
    """Pad string to a target visual width."""
    current = _wcswidth(text) if text else 0
    fill = max(width - current, 0)
    if align == "right":
        return " " * fill + text
    if align == "center":
        return " " * (fill // 2) + text + " " * (fill - fill // 2)
    return text + " " * fill


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]], aligns: Sequence[str] | None = None) -> str:
    """Render a fixed-width text table.

    Each cell value is treated as a string. Numeric columns are right-aligned
    by default if their name contains "数" / "伤害" / "HP" or starts with a digit.
    """
    aligns = list(aligns or ["left"] * len(headers))
    rows = [list(r) for r in rows]
    widths: list[int] = []
    for i, h in enumerate(headers):
        col_vals = [h] + [r[i] if i < len(r) else "" for r in rows]
        widths.append(max(_wcswidth(v) if v else 0 for v in col_vals) + 1)
    out_lines: list[str] = []
    sep = "+".join("-" * w for w in widths)
    sep = f"+{sep}+"
    out_lines.append(sep)
    out_lines.append("|" + "|".join(_pad(h, widths[i] - 1, aligns[i]) for i, h in enumerate(headers)) + "|")
    out_lines.append(sep)
    for r in rows:
        cells = []
        for i, cell in enumerate(r):
            val = str(cell) if cell is not None else ""
            cells.append(_pad(val, widths[i] - 1, aligns[i]))
        out_lines.append("|" + "|".join(cells) + "|")
    out_lines.append(sep)
    return "\n".join(out_lines)


def _right_align_if_numeric(header: str) -> str:
    if any(k in header for k in ("数", "伤害", "HP", "Lv", "lv", "等级", "BuildUp", "Decay")):
        return "right"
    return "left"


# ----------------------------------------------------------------------
# Renderers
# ----------------------------------------------------------------------


def render_help() -> str:
    return (
        "🎮 怪物猎人辅助插件\n"
        "\n"
        "命令前缀: /mh  (中文别名: /mh)\n"
        "作品标识: mhworld / mhrise / mhwilds  (省略时按上次使用 → 默认 mhwilds)\n"
        "\n"
        "怪物相关:\n"
        "  /mh 怪物列表 [game]    - 列出该作大型怪物\n"
        "  /mh 怪物 <名> [game]    - 怪物基础信息\n"
        "  /mh 肉质 <名> [game]    - 肉质表\n"
        "  /mh 弱点 <名> [game]    - 属性弱点与状态异常\n"
        "  /mh 素材 <名> [game]    - 剥取/破坏/目标报酬\n"
        "\n"
        "技能相关:\n"
        "  /mh 技能列表 [game]     - 列出该作技能\n"
        "  /mh 技能 <名> [game]    - 技能各等级效果\n"
        "\n"
        "其他:\n"
        "  /mh 作品                - 列出已启用作品\n"
        "  /mh 更新 [game]         - 管理员: 在线刷新数据\n"
        "  /mh 帮助                - 展示此帮助\n"
    )


def render_games(games: Sequence[str]) -> str:
    lines = ["已启用的作品:"]
    for g in games:
        lines.append(f"  - {g}  ({GAME_LABELS.get(g, g)})")
    return "\n".join(lines)


def render_monster_list(game: str, monsters: Sequence[dict[str, Any]], max_rows: int = 30) -> str:
    rows = []
    for m in monsters:
        zh = m.get("name_zh") or m.get("id") or "?"
        en = m.get("name_en") or ""
        rows.append([zh, en])
    total = len(rows)
    truncated = rows[:max_rows]
    table = _table(["中文名", "英文名"], truncated)
    extra = ""
    if total > max_rows:
        extra = f"\n… 共 {total} 条,本条消息仅展示前 {max_rows} 条。请用具体名字查询。"
    return f"📜 {GAME_LABELS.get(game, game)} — 大型怪物 ({total})\n" + table + extra


def render_skill_list(game: str, skills: Sequence[dict[str, Any]], max_rows: int = 30) -> str:
    rows = []
    for s in skills:
        zh = s.get("name_zh") or s.get("id") or "?"
        en = s.get("name_en") or ""
        lv = len(s.get("levels") or [])
        rows.append([zh, en, str(lv)])
    total = len(rows)
    truncated = rows[:max_rows]
    table = _table(["中文名", "英文名", "等级数"], truncated, ["left", "left", "right"])
    extra = ""
    if total > max_rows:
        extra = f"\n… 共 {total} 条,本条消息仅展示前 {max_rows} 条。"
    return f"📜 {GAME_LABELS.get(game, game)} — 技能 ({total})\n" + table + extra


def render_monster_info(monster: dict[str, Any], game: str) -> str:
    name_zh = monster.get("name_zh") or monster.get("id")
    name_en = monster.get("name_en") or ""
    lines = [f"🐉 {name_zh} ({name_en}) — {GAME_LABELS.get(game, game)}"]
    rows = []
    if monster.get("species"):
        rows.append(["种类", monster["species"]])
    if monster.get("hr_point") is not None:
        rows.append(["HR 点数", str(monster["hr_point"])])
    if monster.get("base_hp") is not None:
        rows.append(["基础 HP", str(monster["base_hp"])])
    if monster.get("aliases"):
        rows.append(["别名", ", ".join(monster["aliases"])])
    if monster.get("id"):
        rows.append(["ID", monster["id"]])
    if rows:
        lines.append(_table(["属性", "值"], rows))
    return "\n".join(lines)


def render_meat(monster: dict[str, Any], game: str, max_rows: int = 30) -> str:
    name_zh = monster.get("name_zh") or monster.get("id")
    name_en = monster.get("name_en") or ""
    meat = monster.get("meat") or {}
    headers: list[str] = list(meat.get("headers") or [])
    rows_raw: list[dict[str, Any]] = list(meat.get("rows") or [])
    if not headers:
        return f"🍖 {name_zh} ({name_en}) — 该作品暂无肉质数据"

    # Build a (header_text -> column_index) map for semantic lookups.
    has_part = any(h in ("部位", "Part") for h in headers)
    has_state = any(h in ("状态", "State") for h in headers)

    aligns = [_right_align_if_numeric(h) for h in headers]
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
        # Pad/trim to header count
        while len(cells) < len(headers):
            cells.append("?")
        body_rows.append(cells[: len(headers)])
    table = _table(headers, body_rows, aligns)
    extra = ""
    if len(rows_raw) > max_rows:
        extra = f"\n… 共 {len(rows_raw)} 行,本条消息仅展示前 {max_rows} 行。"
    return f"🍖 {name_zh} ({name_en}) — 肉质表\n" + table + extra


def render_weak(monster: dict[str, Any], game: str) -> str:
    name_zh = monster.get("name_zh") or monster.get("id")
    name_en = monster.get("name_en") or ""
    lines = [f"⚔️ {name_zh} ({name_en}) — 弱点 & 状态异常"]
    ailments = monster.get("ailments") or {}
    if ailments:
        rows = [[k, str(v)] for k, v in ailments.items()]
        lines.append(_table(["状态异常", "累积值"], rows, ["left", "right"]))
    else:
        lines.append("该作品暂无状态异常数据。")
    # Best meat values summary (extract highest per attribute from meat rows)
    meat = monster.get("meat") or {}
    headers = list(meat.get("headers") or [])
    rows_raw = list(meat.get("rows") or [])
    if headers and rows_raw:
        attr_indices: list[tuple[str, int]] = []
        for i, h in enumerate(headers):
            if h in ("火", "水", "雷", "冰", "龙", "麻"):
                attr_indices.append((h, i - 2))  # values offset (skip part/state columns)
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
            lines.append(_table(["属性", "最大肉质"], [[a, str(v)] for a, v in best], ["left", "right"]))
    return "\n".join(lines)


def render_rewards(monster: dict[str, Any], game: str, max_rows: int = 30) -> str:
    name_zh = monster.get("name_zh") or monster.get("id")
    name_en = monster.get("name_en") or ""
    rewards = monster.get("rewards") or {}
    if not rewards:
        return f"💎 {name_zh} ({name_en}) — 该作品暂无报酬数据"
    lines = [f"💎 {name_zh} ({name_en}) — 素材报酬"]
    for category, items in rewards.items():
        lines.append(f"\n▸ {category}")
        if not items:
            lines.append("  (无数据)")
            continue
        truncated = items[:max_rows]
        rows = []
        for it in truncated:
            if isinstance(it, dict):
                rows.append([str(it.get("item") or "?"), str(it.get("rate") or "?")])
            else:
                rows.append([str(it), ""])
        lines.append(_table(["素材", "概率"], rows, ["left", "right"]))
        if len(items) > max_rows:
            lines.append(f"  … 共 {len(items)} 条,本条消息仅展示前 {max_rows} 条。")
    return "\n".join(lines)


def render_skill(skill: dict[str, Any], game: str) -> str:
    name_zh = skill.get("name_zh") or skill.get("id")
    name_en = skill.get("name_en") or ""
    levels = skill.get("levels") or []
    lines = [f"📘 {name_zh} ({name_en}) — {GAME_LABELS.get(game, game)}"]
    if not levels:
        lines.append("该作品暂无技能效果数据。")
        return "\n".join(lines)
    rows = []
    for lv in levels:
        if isinstance(lv, dict):
            rows.append([str(lv.get("lv") or "?"), str(lv.get("effect") or "?")])
        else:
            rows.append(["?", str(lv)])
    lines.append(_table(["等级", "效果"], rows, ["right", "left"]))
    return "\n".join(lines)


def render_error(title: str, detail: str, suggestions: list[str] | None = None) -> str:
    msg = f"⚠️ {title}\n{detail}"
    if suggestions:
        msg += "\n\n你可能想查:\n" + "\n".join(f"  - {s}" for s in suggestions)
    return msg


def render_update_result(game: str, monsters: int, skills: int, seconds: float) -> str:
    return f"✅ 已更新 {GAME_LABELS.get(game, game)}: 怪物 {monsters} 条,技能 {skills} 条。耗时 {seconds:.1f}s"