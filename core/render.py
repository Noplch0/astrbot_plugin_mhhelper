"""Delivery helpers: pick an output mode, and convert formatter markdown.

The formatter (:mod:`core.formatter`) always produces markdown. Whether the
user can actually *see* markdown depends entirely on the chat platform, so this
module owns the two degradation paths plus the mode policy:

``markdown``
    Send the markdown text as-is. Correct for Telegram / Lark / Discord / …,
    which render it natively.

``image``
    Render the markdown as an HTML card and screenshot it (AstrBot's built-in
    文转图). This is the only way tables survive **QQ 个人号 (aiocqhttp)**: it
    renders neither markdown nor whitespace-aligned plain text, so a picture is
    the only readable option.

``text``
    Degrade markdown to aligned plain text.

Everything here is dependency-free — no markdown library, no AstrBot import —
so it is unit-testable offline. Only a deliberately small markdown subset is
understood, which is exactly the subset :mod:`core.formatter` emits:

* ``##`` / ``###`` headings
* ``-`` bullet lists
* GFM pipe tables (with a ``| :--- | ---: |`` separator row)
* inline ``**bold**`` and `` `code` ``
* ``---`` horizontal rules
"""
from __future__ import annotations

import html
import re

from .formatter import light_table

# ----------------------------------------------------------------------
# Output modes
# ----------------------------------------------------------------------

MODES: tuple[str, ...] = ("auto", "text", "markdown", "image")

#: 这些平台会原生渲染 markdown，auto 模式下直接发文本。
_MARKDOWN_PLATFORMS: frozenset[str] = frozenset(
    {
        "telegram",
        "lark",
        "feishu",
        "discord",
        "slack",
        "misskey",
        "satori",
        "webchat",
    }
)

#: 这些平台不渲染 markdown，auto 模式下转成图片才好看（QQ 全系）。
_IMAGE_PLATFORMS: frozenset[str] = frozenset(
    {
        "aiocqhttp",
        "qq_official",
        "qq_official_webhook",
        "wecom",
        "wecom_ai_bot",
        "dingtalk",
        "kook",
        "weixin_official_account",
        "wxauto",
        "bilibili",
    }
)


def resolve_mode(mode: str | None, platform: str | None) -> str:
    """Return the concrete mode (``text``/``markdown``/``image``) to use.

    ``auto`` inspects the platform; an explicit mode is passed through (and
    anything unrecognised falls back to ``auto``).
    """
    chosen = (mode or "auto").strip().lower()
    if chosen not in MODES:
        chosen = "auto"
    if chosen != "auto":
        return chosen
    name = (platform or "").strip().lower().replace("-", "_")
    if name in _MARKDOWN_PLATFORMS:
        return "markdown"
    if name in _IMAGE_PLATFORMS:
        return "image"
    return "text"


def mode_hint(mode: str) -> str:
    """Short human-readable explanation, used by the 帮助 output / logs."""
    return {
        "text": "纯文本（空格对齐）",
        "markdown": "markdown 文本",
        "image": "图片卡片",
    }.get(mode, "纯文本（空格对齐）")


# ----------------------------------------------------------------------
# Markdown parsing (restricted subset)
# ----------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_HR = re.compile(r"^\s*-{3,}\s*$")
_SEP_CELL = re.compile(r"^:?-{1,}:?$")
#: split on ``|`` that is not escaped as ``\|``
_PIPE = re.compile(r"(?<!\\)\|")


def _split_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    return [cell.strip().replace("\\|", "|") for cell in _PIPE.split(text)]


def _is_separator(line: str) -> bool:
    cells = _split_row(line)
    return bool(cells) and all(c and _SEP_CELL.match(c) for c in cells)


def _parse_aligns(line: str) -> list[str]:
    aligns = []
    for cell in _split_row(line):
        if cell.startswith(":") and cell.endswith(":"):
            aligns.append("center")
        elif cell.endswith(":"):
            aligns.append("right")
        else:
            aligns.append("left")
    return aligns


def _is_table_start(lines: list[str], i: int) -> bool:
    return (
        lines[i].lstrip().startswith("|")
        and i + 1 < len(lines)
        and _is_separator(lines[i + 1])
    )


def _strip_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def _inline_html(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


# ----------------------------------------------------------------------
# markdown → plain text
# ----------------------------------------------------------------------


def markdown_to_plaintext(md: str) -> str:
    """Degrade formatter markdown to whitespace-aligned plain text."""
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    total = len(lines)
    while i < total:
        line = lines[i]
        if _is_table_start(lines, i):
            headers = _split_row(line)
            i += 2
            rows: list[list[str]] = []
            while i < total and lines[i].lstrip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            out.append(light_table(headers, rows))
            continue
        match = _HEADING.match(line)
        if match:
            out.append(_strip_inline(match.group(2)))
            i += 1
            continue
        if _HR.match(line):
            out.append("─" * 24)
            i += 1
            continue
        bullet = _BULLET.match(line)
        if bullet:
            out.append("  • " + _strip_inline(bullet.group(1)))
            i += 1
            continue
        out.append(_strip_inline(line))
        i += 1
    return "\n".join(out).strip("\n")


# ----------------------------------------------------------------------
# markdown → HTML (for the image card)
# ----------------------------------------------------------------------


def _table_html(headers: list[str], aligns: list[str], rows: list[list[str]]) -> str:
    width = len(headers)

    def _align(i: int) -> str:
        return aligns[i] if i < len(aligns) else "left"

    def _cells(tag: str, values: list[str]) -> str:
        padded = values[:width] + [""] * max(width - len(values), 0)
        return "".join(
            f'<{tag} class="{_align(i)}">{_inline_html(v)}</{tag}>'
            for i, v in enumerate(padded)
        )

    head = _cells("th", headers)
    body = "".join(f"<tr>{_cells('td', row)}</tr>" for row in rows)
    return (
        "<table>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
    )


def markdown_to_html(md: str) -> str:
    """Convert formatter markdown into the HTML fragment inside the card."""
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    total = len(lines)
    while i < total:
        line = lines[i]
        if _is_table_start(lines, i):
            headers = _split_row(line)
            aligns = _parse_aligns(lines[i + 1])
            i += 2
            rows: list[list[str]] = []
            while i < total and lines[i].lstrip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            out.append(_table_html(headers, aligns, rows))
            continue
        match = _HEADING.match(line)
        if match:
            level = min(len(match.group(1)) + 1, 6)
            out.append(f"<h{level}>{_inline_html(match.group(2))}</h{level}>")
            i += 1
            continue
        if _HR.match(line):
            out.append("<hr>")
            i += 1
            continue
        bullet = _BULLET.match(line)
        if bullet:
            items = []
            while i < total:
                more = _BULLET.match(lines[i])
                if not more:
                    break
                items.append(_inline_html(more.group(1)))
                i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue
        if not line.strip():
            i += 1
            continue
        out.append(f"<p>{_inline_html(line)}</p>")
        i += 1
    return "\n".join(out)


# ----------------------------------------------------------------------
# Image card template (rendered by AstrBot's 文转图 / Star.html_render)
# ----------------------------------------------------------------------

CARD_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  html, body { margin:0; padding:0; background:#eef1f6; }
  body {
    font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",
                "Noto Sans CJK SC",system-ui,-apple-system,sans-serif;
    font-size:15px; line-height:1.65; color:#1f2430;
  }
  .card {
    box-sizing:border-box;
    display:inline-block;
    margin:14px;
    padding:18px 22px 20px;
    min-width:320px;
    max-width:920px;
    background:#ffffff;
    border:1px solid #e6eaf2;
    border-radius:14px;
    box-shadow:0 6px 22px rgba(31,36,48,.13);
  }
  h2, h3 { margin:.6em 0 .45em; line-height:1.3; }
  h2 { font-size:19px; }
  h3 { font-size:16px; color:#2f3b52; }
  h2:first-child, h3:first-child, p:first-child, ul:first-child, table:first-child {
    margin-top:0;
  }
  p { margin:.35em 0; }
  ul { margin:.35em 0; padding-left:1.35em; }
  li { margin:.14em 0; }
  hr { border:0; border-top:1px solid #e6eaf2; margin:.85em 0; }
  code {
    font-family:"JetBrains Mono","Cascadia Code",Consolas,monospace;
    font-size:.86em; background:#eef1f7; color:#b04a00;
    padding:1px 5px; border-radius:5px;
  }
  table {
    border-collapse:collapse; margin:.5em 0 0; font-size:14px;
    font-variant-numeric:tabular-nums;
  }
  th, td { border:1px solid #dde3ee; padding:5px 10px; white-space:nowrap; }
  th { background:#2f3b52; color:#ffffff; font-weight:600; }
  tbody tr:nth-child(even) td { background:#f6f8fc; }
  .left { text-align:left; }
  .right { text-align:right; }
  .center { text-align:center; }
</style>
</head>
<body>
<div class="card">{{ content | safe }}</div>
</body>
</html>
"""


__all__ = [
    "CARD_TEMPLATE",
    "MODES",
    "markdown_to_html",
    "markdown_to_plaintext",
    "mode_hint",
    "resolve_mode",
]
