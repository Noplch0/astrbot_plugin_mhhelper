"""Unit tests for core.render — the markdown degradation + mode policy layer."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from core.formatter import md_table
from core.render import (
    CARD_RENDER_OPTIONS,
    CARD_TEMPLATE,
    MODES,
    markdown_to_html,
    markdown_to_plaintext,
    resolve_mode,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _display_width(text: str) -> int:
    """CJK-aware width, so padded plain-text rows can be compared."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


MD = "\n".join(
    [
        "## 🐉 雌火龙 (Rathian)",
        "",
        "- **种类**：飞龙种",
        "- **基础 HP**：4500",
        "",
        "| 部位 | 状态 | 斩 |",
        "| :--- | :--- | ---: |",
        "| 头部 | 通常 | 70 |",
        "| 躯干 | 通常 | 35 |",
    ]
)


# --------------------------------------------------------------------------
# 模式决策
# --------------------------------------------------------------------------


def test_modes_tuple():
    assert MODES == ("auto", "text", "markdown", "image")


@pytest.mark.parametrize("mode", ["text", "markdown", "image"])
def test_explicit_mode_is_passed_through(mode):
    """显式指定的模式不受平台影响。"""
    assert resolve_mode(mode, "aiocqhttp") == mode
    assert resolve_mode(mode, "telegram") == mode


@pytest.mark.parametrize(
    "platform", ["aiocqhttp", "qq_official", "wecom", "DingTalk", "kook", "bilibili"]
)
def test_auto_picks_image_for_qq_like_platforms(platform):
    assert resolve_mode("auto", platform) == "image"


@pytest.mark.parametrize("platform", ["telegram", "lark", "Discord", "Slack", "webchat"])
def test_auto_picks_markdown_for_markdown_platforms(platform):
    assert resolve_mode("auto", platform) == "markdown"


def test_auto_unknown_platform_is_text():
    assert resolve_mode("auto", "some_brand_new_adapter") == "text"
    assert resolve_mode("auto", "") == "text"
    assert resolve_mode("auto", None) == "text"


def test_unknown_mode_falls_back_to_auto():
    assert resolve_mode("bogus", "telegram") == "markdown"
    assert resolve_mode("", "aiocqhttp") == "image"
    assert resolve_mode(None, None) == "text"


# --------------------------------------------------------------------------
# markdown → 纯文本
# --------------------------------------------------------------------------


def test_plaintext_strips_markdown_markers():
    txt = markdown_to_plaintext(MD)
    assert "##" not in txt
    assert "**" not in txt
    assert "|" not in txt
    assert ":---" not in txt
    assert "🐉 雌火龙 (Rathian)" in txt


def test_plaintext_bullets_keep_content():
    txt = markdown_to_plaintext(MD)
    assert "  • 种类：飞龙种" in txt
    assert "  • 基础 HP：4500" in txt


def test_plaintext_table_is_rebuilt_as_aligned_columns():
    txt = markdown_to_plaintext(MD)
    rows = [l for l in txt.splitlines() if l.strip()]
    assert rows[-2].startswith("头部")
    assert rows[-1].startswith("躯干")
    assert rows[-1].rstrip().endswith("35")
    # 表头 + 数据行的显示宽度一致（CJK 按双宽计算）
    widths = {_display_width(l) for l in rows[-3:]}
    assert len(widths) == 1, rows[-3:]


def test_plaintext_escaped_pipe_survives():
    md = md_table(["说明"], [["a|b"]])
    assert "a|b" in markdown_to_plaintext(md)


# --------------------------------------------------------------------------
# markdown → HTML（图片卡片）
# --------------------------------------------------------------------------


def test_html_table_structure_and_alignment():
    out = markdown_to_html(MD)
    assert "<table>" in out
    assert '<th class="left">部位</th>' in out
    assert '<th class="right">斩</th>' in out
    assert '<td class="left">头部</td>' in out
    assert '<td class="right">70</td>' in out
    assert out.count("<tr>") == 3  # thead + 2 body rows


def test_html_headings_bullets_and_bold():
    out = markdown_to_html(MD)
    assert "<h3>🐉 雌火龙 (Rathian)</h3>" in out
    assert "<ul>" in out
    assert "<li><strong>种类</strong>：飞龙种</li>" in out


def test_html_inline_code():
    out = markdown_to_html("- `/mh 肉质 火龙`")
    assert "<code>/mh 肉质 火龙</code>" in out


def test_html_escapes_raw_markup():
    out = markdown_to_html("| a |\n| :--- |\n| <script>alert(1)</script> |")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_html_escaped_pipe_is_one_cell():
    md = md_table(["部位", "说明"], [["头部", "a|b"]])
    out = markdown_to_html(md)
    assert "a\\|b" in md
    assert '<td class="left">a|b</td>' in out


def test_md_table_right_aligns_numeric_headers():
    md = md_table(["部位", "伤害"], [["头部", 70]])
    assert "---:" in md.splitlines()[1]


def test_card_template_content_slot_and_styles():
    assert "{{ content | safe }}" in CARD_TEMPLATE
    assert "<style>" in CARD_TEMPLATE
    assert "table" in CARD_TEMPLATE


# --------------------------------------------------------------------------
# 图片卡片模板：必须铺满画布、字号够大（v0.3.3）
# --------------------------------------------------------------------------
# 实测反馈是「图片太模糊且信息集中在左上角」。原因是模板用了收缩包裹的卡片
# （卡片只有 ~345px，画布 ~800px，右边一大片空白），字号又只有 15px（被 QQ
# 缩放后糊成一团）。官方 base.html 的基准是 font-size:25px +
# main { width: min(100%, 920px) }，所以这里把这两条钉死。
#
# 断言前先剥掉 CSS 注释 —— 模板里会在注释中说明"以前用的是收缩包裹"，那不该
# 影响样式断言。
_CARD_CSS = re.sub(r"/\*.*?\*/", "", CARD_TEMPLATE, flags=re.S)


def test_card_is_not_shrink_wrapped():
    """收缩包裹会让内容缩在左上角 —— 这是被投诉的那个 bug。"""
    assert "inline-block" not in _CARD_CSS


def test_card_fills_the_canvas():
    assert "width: max-content" in _CARD_CSS  # 宽表格能撑开卡片
    assert "min-width: 100%" in _CARD_CSS  # 短内容也铺满画布宽度
    assert "min-height: calc(100vh - 50px)" in _CARD_CSS  # 纵向填满默认视口


def test_card_font_is_large_enough_for_a_phone():
    """15px 被缩放后不可读；官方模板用 25px，我们至少 22px。"""
    match = re.search(r"\n\s*font-size:\s*(\d+)px", _CARD_CSS)
    assert match, "body 应该有明确的 px 字号"
    assert int(match.group(1)) >= 22


def test_card_centers_vertically_without_clipping_overflow():
    """内容短时纵向居中；内容超出时必须退回顶部，不能把表头裁掉。"""
    assert "justify-content: safe center" in _CARD_CSS


def test_card_render_options_raise_the_jpeg_quality():
    """AstrBot 默认 {"full_page":True,"type":"jpeg","quality":40}，40 会发糊。"""
    assert CARD_RENDER_OPTIONS["quality"] > 40
    assert set(CARD_RENDER_OPTIONS) == {"quality"}, (
        "只覆盖 quality：其余键沿用 AstrBot 默认值，避免端点不认新键"
    )


# --------------------------------------------------------------------------
# light_table 导入兼容性（v0.3.1）
# --------------------------------------------------------------------------


def test_light_table_is_reexported_from_render():
    from core import formatter, render

    assert callable(render.light_table)
    assert render.light_table is formatter.light_table


def test_plaintext_table_path_uses_light_table():
    """text 模式仍然依赖 light_table，所以它必须一直可导入。"""
    md = md_table(["部位", "伤害"], [["头部", 70]])
    txt = markdown_to_plaintext(md)
    assert "部位" in txt and "70" in txt
    assert "|" not in txt


def test_render_keeps_a_legacy_fallback_for_light_table():
    """旧 formatter（< v0.3.0）只导出私有名 `_light_table`。

    AstrBot 更新插件时若只替换了部分文件（旧 formatter + 新 render），
    以前会在加载期直接抛
    ``cannot import name 'light_table' from 'core.formatter'`` 把整个插件
    打挂。这里锁住那条兼容分支，防止它被无意删掉。
    """
    src = (REPO_ROOT / "core" / "render.py").read_text(encoding="utf-8")
    assert "from .formatter import light_table" in src
    assert "from .formatter import _light_table as light_table" in src
