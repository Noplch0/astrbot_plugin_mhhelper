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
from typing import Any, Iterable, Mapping, Sequence

from .data_loader import GAME_LABELS

# ----------------------------------------------------------------------
# Column / label vocabulary
# ----------------------------------------------------------------------

#: 肉质表里属于「属性」的列。注意**不含「麻」**：kiranico 那一列虽然写着「麻」，
#: 数值实际是**晕厥**（同一个表里状态异常已经有独立的麻痹行了），所以它既不该
#: 出现在属性弱点概览里，也不是属性。
_ELEMENT_COLUMNS: frozenset[str] = frozenset({"火", "水", "雷", "冰", "龙"})

#: 状态异常名的显示别名 —— 统一压成单字，横排更好扫读。
#: 英文键来自世界的 kiranico 页（那一页混入了英文行）。
_AILMENT_LABELS: dict[str, str] = {
    "毒": "毒",
    "睡眠": "眠",
    "麻痹": "麻",
    "爆破异常": "爆",
    "昏厥": "晕",
    "减气": "减气",
    "Stamina": "减气",
    "Mount": "骑乘",
    "Captures": "捕获",
    "Elderseal": "龙封",
}


def _ailment_label(key: str) -> str:
    """单字展示状态异常；没登记过的键原样返回（宁可长一点也不要丢信息）。"""
    return _AILMENT_LABELS.get(key, key)

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
#: 状态异常那几列（毒/眠/麻/爆/晕/减气…）也全是数字，一并列进来。
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
    "爆",
    "晕",
    "减气",
    "骑乘",
    "捕获",
    "龙封",
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


def _display_name(item: Mapping[str, Any], fallback: str = "?") -> str:
    """中文名 → 英文名 → id。

    **绝不把内部 id 当名字显示** —— 崛起/世界的 id 是 `1301934382` / `KpViL` 这种，
    直接显示出来就是用户看到的「乱码」。中文名优先，其次英文名（可读），
    只有在两者都没有时才退回 id（用于排查）。
    """
    name_zh = str(item.get("name_zh") or "").strip()
    name_en = str(item.get("name_en") or "").strip()
    if name_zh and name_en and name_zh != name_en:
        return f"{name_zh} ({name_en})"
    if name_zh:
        return name_zh
    if name_en:
        return name_en
    return str(item.get("id") or fallback)


#: 属性弱点的稳定排序顺序（数值相同时按这个先后）。
_ELEMENT_ORDER: tuple[str, ...] = ("火", "水", "雷", "冰", "龙")

#: `/mh 怪物` 的属性弱点只列最强的几项。
_WEAKNESS_TOP_N = 2


def _element_weakness(monster: Mapping[str, Any]) -> list[tuple[str, int]]:
    """属性弱点 = 各部位最大值，按数值降序（同值按 火水雷冰龙）。

    只保留 >0 的：全 0 的属性不叫弱点，列出来只是占位。
    注意 kiranico 肉质表最后一列写着「麻」，但那个数值其实是**晕厥**，
    所以属性只认 :data:`_ELEMENT_COLUMNS`。
    """
    meat = monster.get("meat") or {}
    headers = list(meat.get("headers") or [])
    rows = list(meat.get("rows") or [])
    best: list[tuple[str, int]] = []
    for index, header in enumerate(headers):
        if header not in _ELEMENT_COLUMNS:
            continue
        idx = index - 2  # 跳过前置的「部位」「状态」两列
        values: list[int] = []
        for row in rows:
            cells = list(row.get("values") or [])
            if 0 <= idx < len(cells):
                values.append(int(cells[idx] or 0))
        if values:
            best.append((header, max(values)))
    positives = [(k, v) for k, v in best if v > 0]
    return sorted(positives, key=lambda kv: (-kv[1], _ELEMENT_ORDER.index(kv[0])))


def _weakness_section(monster: Mapping[str, Any]) -> list[str]:
    """属性弱点：只列最强的 :data:`_WEAKNESS_TOP_N` 项，并带上具体数值。"""
    lines = ["### 属性弱点"]
    best = _element_weakness(monster)
    if not best:
        lines.append("- 无属性弱点（各属性在所有部位都是 0）")
        return lines
    for attribute, value in best[:_WEAKNESS_TOP_N]:
        lines.append(f"- **{attribute}**：{value}")
    return lines


def _ailments_section(monster: Mapping[str, Any]) -> list[str]:
    """异常累积：横过来排 —— 第一行是异常种类，第二行才是数值。"""
    ailments = monster.get("ailments") or {}
    lines = ["### 异常累积"]
    if not ailments:
        lines.append("- 该作品暂无状态异常数据。")
        return lines
    labels = [_ailment_label(key) for key in ailments]
    values = [str(value) for value in ailments.values()]
    lines += ["", md_table(labels, [values])]
    return lines


def _meat_section(monster: Mapping[str, Any], game: str, max_rows: int) -> list[str]:
    lines = ["### 肉质表"]
    meat = monster.get("meat") or {}
    headers: list[str] = list(meat.get("headers") or [])
    rows_raw: list[dict[str, Any]] = list(meat.get("rows") or [])
    if not headers:
        lines.append(f"- {GAME_LABELS.get(game, game)} 暂无肉质数据。")
        return lines

    has_part = any(h in ("部位", "Part") for h in headers)
    has_state = any(h in ("状态", "State") for h in headers)

    body_rows: list[list[str]] = []
    for row in rows_raw[:max_rows]:
        cells: list[str] = []
        if has_part:
            cells.append(str(row.get("part") or ""))
        if has_state:
            cells.append(str(row.get("state") or "通常"))
        for value in row.get("values") or []:
            cells.append(str(value))
        while len(cells) < len(headers):
            cells.append("?")
        body_rows.append(cells[: len(headers)])

    lines += ["", md_table(headers, body_rows)]
    if len(rows_raw) > max_rows:
        lines += ["", f"… 共 {len(rows_raw)} 行，本条消息仅展示前 {max_rows} 行。"]
    return lines


def render_monster_report(
    monster: Mapping[str, Any], game: str, max_rows: int = 30
) -> str:
    """`/mh 怪物` 的合并报告（基础信息 / 肉质 / 弱点三合一）。

    顺序固定：**怪物名 → 属性弱点 → 肉质表 → 异常累积**。
    图片模式下卡片顶部还会额外居中显示怪物图标（见 :mod:`core.render`），
    文本模式只是把同一份 markdown 降级成纯文本，所以两边顺序完全一致。
    """
    blocks = [
        [f"## {_display_name(monster)}"],
        _weakness_section(monster),
        _meat_section(monster, game, max_rows),
        _ailments_section(monster),
    ]
    return "\n\n".join("\n".join(block) for block in blocks if block)


# ----------------------------------------------------------------------
# Renderers — every one of these returns markdown.
# ----------------------------------------------------------------------


def render_help() -> str:
    return "\n".join(
        [
            "## 怪物猎人查询",
            "",
            "全部查询都收在 `/mh` 指令组下，格式：`/mh <子命令> [名字] [作品]`",
            "",
            "### 查询怪物（基础信息 / 肉质 / 弱点 合并成一条）",
            "- `/mh 怪物 <名字> [作品]` — 依次给出：怪物名 → 属性弱点（最强两项）"
            " → 肉质表 → 异常累积（状态异常）",
            "- 图片模式下卡片顶部还会居中显示该怪物的图鉴图标",
            "",
            "### 技能",
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
            "`monster` / `meat` / `weak` / `skill` / `games` / `update` / `help`",
            "",
            "### 示例",
            "- `/mh 怪物 火龙`",
            "- `/mh monster Rathian 荒野`",
            "- `/mh 技能 攻击 mhrise`",
        ]
    )


def render_games(games: Sequence[str]) -> str:
    lines = ["## 已启用的作品", ""]
    if not games:
        lines.append("- （无：请管理员在插件配置中启用至少一个作品）")
        return "\n".join(lines)
    for g in games:
        lines.append(f"- **{GAME_LABELS.get(g, g)}** — `{g}`")
    return "\n".join(lines)


def render_skill(skill: dict[str, Any], game: str) -> str:
    levels = skill.get("levels") or []
    lines = [f"## {_display_name(skill)} — {GAME_LABELS.get(game, game)}", ""]
    if not levels:
        lines.append("该作品暂无技能效果数据。")
        return "\n".join(lines)
    for lv in levels:
        if isinstance(lv, dict):
            lv_str = str(lv.get("lv") or "?")
            effect = str(lv.get("effect") or "").strip()
            # kiranico 自己有些等级就是空描述（例：抑制偏移 Lv3），
            # 空的时候别留一个尾随空格。
            lines.append(f"- **Lv {lv_str}** {effect}" if effect else f"- **Lv {lv_str}**")
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
    "render_monster_report",
    "render_skill",
    "render_update_result",
]
