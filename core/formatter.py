"""Markdown formatter for monster / skill data.

Every ``render_*`` function returns **GitHub-Flavored Markdown**. How that
markdown reaches the user is decided further downstream (see ``core/render.py``
and the plugin's ``_emit`` step), because the answer depends on the platform:

* ``markdown`` mode — send the markdown as-is (Telegram, Lark, Discord, …).
* ``image``    mode — turn it into an HTML card and screenshot it. This is the
  only way to show tables on **QQ 个人号 (aiocqhttp)**, which renders neither
  markdown nor fixed-width plain text.
* ``text``     mode — degrade it to aligned plain text via
  :func:`core.render.markdown_to_plaintext`.

To keep all three paths dependency-free, the markdown emitted here is
deliberately restricted to a small subset:

* ``##`` / ``###`` headings
* ``-`` bullet lists
* GFM pipe tables (``| a | b |`` + a ``| :--- | ---: |`` separator row)
* inline ``**bold**`` and `` `code` ``
* ``---`` horizontal rules

Nothing here imports a markdown library or AstrBot.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Iterable, Sequence

from .data_loader import GAME_LABELS

# ----------------------------------------------------------------------
# CJK-aware width helpers (used by the plain-text degradation path)
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
# Column alignment — shared by the markdown table and the plain-text table.
# Numeric-looking columns are right-aligned/right-flushed.
# ----------------------------------------------------------------------

#: 列头命中这些子串时右对齐。既包含普适的数值词，也包含肉质表的
#: 斩/打/弹/火水雷冰龙 等属性列——那些列全是数字，右对齐更易横向比较。
_NUMERIC_HINTS = (
    "数",
    "伤害",
    "HP",
    "Lv",
    "等级",
    "BuildUp",
    "Decay",
    "概率",
    "率",
    "点数",
    "斩",
    "打",
    "弹",
    "火",
    "水",
    "雷",
    "冰",
    "龙",
    "麻",
    "眠",
    "毒",
    "爆破",
)


def _align_for(header: str) -> str:
    return "right" if any(k in header for k in _NUMERIC_HINTS) else "left"


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def md_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Render a GFM pipe table.

    Pipes inside a cell are escaped so the table stays parseable by the
    markdown → HTML / plain-text converters.
    """
    heads = [str(h) for h in headers]
    body = [[_cell(v) for v in r] for r in rows]

    def _fmt(cells: Sequence[str]) -> str:
        padded = list(cells[: len(heads)]) + [""] * max(len(heads) - len(cells), 0)
        return "| " + " | ".join(c.replace("|", "\\|") for c in padded) + " |"

    separator = [
        "---:" if _align_for(h) == "right" else ":---" for h in heads
    ]
    lines = [_fmt(heads), _fmt(separator)]
    lines.extend(_fmt(r) for r in body)
    return "\n".join(lines)


def light_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Render the plain-text fallback: header row + whitespace-aligned data."""
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

    out = [_fmt_row(headers)]
    out.extend(_fmt_row(r) for r in rows)
    return "\n".join(out)


# Kept for backwards compatibility with earlier revisions of this module.
_light_table = light_table


def _title(emoji: str, monster: dict[str, Any]) -> str:
    name_zh = monster.get("name_zh") or monster.get("id") or "?"
    name_en = monster.get("name_en") or ""
    if name_en and name_en != name_zh:
        return f"{emoji} {name_zh} ({name_en})"
    return f"{emoji} {name_zh}"


# ----------------------------------------------------------------------
# Renderers — every one of these returns markdown.
# ----------------------------------------------------------------------


def render_help() -> str:
    return "\n".join(
        [
            "## 🎮 怪物猎人查询",
            "",
            "全部查询都收在 `/mh` 指令组下，格式：`/mh <子命令> [名字] [作品]`",
            "",
            "### 怪物",
            "- `/mh 怪物列表 [作品]` — 列出该作大型怪物",
            "- `/mh 怪物 <名字> [作品]` — 怪物基础信息（种类 / HR 点数 / HP）",
            "- `/mh 肉质 <名字> [作品]` — 肉质表（斩 / 打 / 弹 / 属性）",
            "- `/mh 弱点 <名字> [作品]` — 属性弱点与状态异常累积",
            "- `/mh 素材 <名字> [作品]` — 剥取 / 破坏 / 目标报酬",
            "",
            "### 技能",
            "- `/mh 技能列表 [作品]` — 列出该作技能",
            "- `/mh 技能 <名字> [作品]` — 技能各等级效果",
            "",
            "### 其他",
            "- `/mh 作品` — 列出已启用的作品",
            "- `/mh 更新 [作品]` — 管理员：在线刷新数据",
            "- `/mh 帮助` — 显示本帮助",
            "",
            "### 作品标识（可省略，省略时按「上次使用 → 默认作品」）",
            "- `mhworld` / `world` / `世界` / `iceborne` — 怪物猎人:世界",
            "- `mhrise` / `rise` / `崛起` / `sunbreak` — 怪物猎人:崛起",
            "- `mhwilds` / `wilds` / `荒野` — 怪物猎人:荒野",
            "",
            "### 子命令英文别名",
            "`meat` / `weak` / `rewards` / `monster` / `monsters` / `skill` / "
            "`skills` / `games` / `update` / `help`",
            "",
            "### 示例",
            "- `/mh 肉质 火龙`",
            "- `/mh meat Rathian 荒野`",
            "- `/mh 技能列表 mhrise`",
        ]
    )


def render_games(games: Sequence[str]) -> str:
    lines = ["## 🎮 已启用的作品", ""]
    if not games:
        lines.append("- （无：请管理员在插件配置中启用至少一个作品）")
        return "\n".join(lines)
    for g in games:
        lines.append(f"- **{GAME_LABELS.get(g, g)}** — `{g}`")
    return "\n".join(lines)


def render_monster_list(game: str, monsters: Sequence[dict[str, Any]], max_rows: int = 30) -> str:
    total = len(monsters)
    truncated = monsters[:max_rows]
    lines = [f"## 📜 {GAME_LABELS.get(game, game)} — 大型怪物 ({total})", ""]
    for m in truncated:
        zh = m.get("name_zh") or m.get("id") or "?"
        en = m.get("name_en") or ""
        if en and en != zh:
            lines.append(f"- {zh} ({en})")
        else:
            lines.append(f"- {zh}")
    if total > max_rows:
        lines.append("")
        lines.append(f"… 共 {total} 条，本条消息仅展示前 {max_rows} 条。请用具体名字查询。")
    return "\n".join(lines)


def render_skill_list(game: str, skills: Sequence[dict[str, Any]], max_rows: int = 30) -> str:
    total = len(skills)
    truncated = skills[:max_rows]
    lines = [f"## 📜 {GAME_LABELS.get(game, game)} — 技能 ({total})", ""]
    for s in truncated:
        zh = s.get("name_zh") or s.get("id") or "?"
        en = s.get("name_en") or ""
        lv = len(s.get("levels") or [])
        if en and en != zh:
            lines.append(f"- {zh} ({en}) — {lv} 级")
        else:
            lines.append(f"- {zh} — {lv} 级")
    if total > max_rows:
        lines.append("")
        lines.append(f"… 共 {total} 条，本条消息仅展示前 {max_rows} 条。")
    return "\n".join(lines)


def render_monster_info(monster: dict[str, Any], game: str) -> str:
    name_en = monster.get("name_en") or ""
    name_zh = monster.get("name_zh") or monster.get("id") or "?"
    head = name_zh if not (name_en and name_en != name_zh) else f"{name_zh} ({name_en})"
    lines = [f"## 🐉 {head}", ""]
    if monster.get("species"):
        lines.append(f"- **种类**：{monster['species']}")
    lines.append(f"- **作品**：{GAME_LABELS.get(game, game)}")
    if monster.get("hr_point") is not None:
        lines.append(f"- **HR 点数**：{monster['hr_point']}")
    if monster.get("base_hp") is not None:
        lines.append(f"- **基础 HP**：{monster['base_hp']}")
    if monster.get("aliases"):
        lines.append(f"- **别名**：{', '.join(monster['aliases'])}")
    if monster.get("id"):
        lines.append(f"- **ID**：`{monster['id']}`")
    return "\n".join(lines)


def render_meat(monster: dict[str, Any], game: str, max_rows: int = 30) -> str:
    name_zh = monster.get("name_zh") or monster.get("id") or "?"
    meat = monster.get("meat") or {}
    headers: list[str] = list(meat.get("headers") or [])
    rows_raw: list[dict[str, Any]] = list(meat.get("rows") or [])
    if not headers:
        return f"### 🍖 {name_zh} — 该作品暂无肉质数据"

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

    lines = [f"### {_title('🍖', monster)} — 肉质表", "", md_table(headers, body_rows)]
    if len(rows_raw) > max_rows:
        lines.append("")
        lines.append(f"… 共 {len(rows_raw)} 行，本条消息仅展示前 {max_rows} 行。")
    return "\n".join(lines)


def render_weak(monster: dict[str, Any], game: str) -> str:
    lines = [f"## {_title('⚔️', monster)}"]
    ailments = monster.get("ailments") or {}
    lines.append("")
    if ailments:
        lines.append("### 状态异常累积值")
        for k, v in ailments.items():
            lines.append(f"- **{k}**：{v}")
    else:
        lines.append("该作品暂无状态异常数据。")

    # 属性弱点概览（取各部位最大值）
    meat = monster.get("meat") or {}
    headers = list(meat.get("headers") or [])
    rows_raw = list(meat.get("rows") or [])
    if headers and rows_raw:
        best: list[tuple[str, int]] = []
        for i, h in enumerate(headers):
            if h not in ("火", "水", "雷", "冰", "龙", "麻"):
                continue
            idx = i - 2  # 跳过前置的「部位」「状态」两列
            vals = []
            for r in rows_raw:
                v = r.get("values") or [0] * (idx + 1)
                if 0 <= idx < len(v):
                    vals.append(int(v[idx] or 0))
            if vals:
                best.append((h, max(vals)))
        if best:
            lines.append("")
            lines.append("### 属性弱点概览（各部位最大值）")
            for attr, v in best:
                lines.append(f"- **{attr}**：{v}")
    return "\n".join(lines)


def render_rewards(monster: dict[str, Any], game: str, max_rows: int = 30) -> str:
    name_zh = monster.get("name_zh") or monster.get("id") or "?"
    rewards = monster.get("rewards") or {}
    if not rewards:
        return f"### 💎 {name_zh} — 该作品暂无报酬数据"
    lines = [f"### {_title('💎', monster)} — 素材报酬"]
    for category, items in rewards.items():
        lines.append("")
        lines.append(f"**▸ {category}**")
        if not items:
            lines.append("- （无数据）")
            continue
        truncated = items[:max_rows]
        for it in truncated:
            if isinstance(it, dict):
                item = str(it.get("item") or "?")
                rate = str(it.get("rate") or "")
                lines.append(f"- {item} — {rate}" if rate else f"- {item}")
            else:
                lines.append(f"- {it}")
        if len(items) > max_rows:
            lines.append(f"- … 共 {len(items)} 条，本条消息仅展示前 {max_rows} 条。")
    return "\n".join(lines)


def render_skill(skill: dict[str, Any], game: str) -> str:
    name_en = skill.get("name_en") or ""
    name_zh = skill.get("name_zh") or skill.get("id") or "?"
    head = name_zh if not (name_en and name_en != name_zh) else f"{name_zh} ({name_en})"
    levels = skill.get("levels") or []
    lines = [f"## 📘 {head} — {GAME_LABELS.get(game, game)}", ""]
    if not levels:
        lines.append("该作品暂无技能效果数据。")
        return "\n".join(lines)
    for lv in levels:
        if isinstance(lv, dict):
            lv_str = str(lv.get("lv") or "?")
            effect = str(lv.get("effect") or "?").strip()
            lines.append(f"- **Lv {lv_str}** {effect}")
        else:
            lines.append(f"- {lv}")
    return "\n".join(lines)


def render_error(title: str, detail: str, suggestions: list[str] | None = None) -> str:
    lines = [f"⚠️ **{title}**", detail]
    if suggestions:
        lines.append("")
        lines.append("**你可能想查:**")
        for s in suggestions:
            lines.append(f"- {s}")
    return "\n".join(lines)


def render_update_result(game: str, monsters: int, skills: int, seconds: float) -> str:
    return "\n".join(
        [
            f"✅ **已更新 {GAME_LABELS.get(game, game)}**",
            "",
            f"- 怪物：{monsters} 条",
            f"- 技能：{skills} 条",
            f"- 耗时：{seconds:.1f}s",
        ]
    )


__all__ = [
    "light_table",
    "md_table",
    "render_error",
    "render_games",
    "render_help",
    "render_meat",
    "render_monster_info",
    "render_monster_list",
    "render_rewards",
    "render_skill",
    "render_skill_list",
    "render_update_result",
    "render_weak",
]
