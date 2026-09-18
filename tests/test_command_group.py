"""Regression tests for how the plugin registers itself with AstrBot.

The whole plugin must expose exactly **one** top-level command — the `mh`
command group — so AstrBot's 「指令管理」 page renders a single collapsible `mh`
row, with the second-level sub-commands (and their descriptions) nested
underneath. Registering each feature as its own top-level command is what made
the panel unreadable before.

These tests exercise the real ``main.py`` against a stand-in for AstrBot's
registration + filter layer (``tests/_astrbot_fake.py``), and run the handlers
against the offline fixtures in ``tests/fixtures/``.
"""
from __future__ import annotations

import pytest

from ._astrbot_fake import (
    ADMIN,
    dispatch,
    install,
    load_plugin,
    make_plugin,
    registry,
    root_groups,
    top_level_commands,
)
from ._setup import install_fake_loader

install()
MOD = load_plugin()

#: 文转图的渲染参数。取 `main.py` 实际用的那个对象 —— 它的导入引导会重建
#: `core.*` 模块，在这里另 import 一份会拿到另一个副本。
CARD_RENDER_OPTIONS = MOD.CARD_RENDER_OPTIONS

#: (子命令, 别名, 处理函数名) —— 顺序即面板/树形结构中的展示顺序。
EXPECTED_SUBCOMMANDS = [
    ("帮助", {"help", "用法"}, "mh_help"),
    ("怪物列表", {"monsters", "怪物表", "list"}, "mh_monsters"),
    ("怪物", {"monster", "info"}, "mh_monster"),
    ("肉质", {"meat", "肉"}, "mh_meat"),
    ("弱点", {"weak", "属性"}, "mh_weak"),
    ("素材", {"rewards", "报酬", "掉落"}, "mh_rewards"),
    ("技能列表", {"skills", "技能表"}, "mh_skills"),
    ("技能", {"skill"}, "mh_skill"),
    ("作品", {"games", "game"}, "mh_games"),
    ("更新", {"update", "刷新"}, "mh_update"),
]


@pytest.fixture()
def plugin(monkeypatch, tmp_path):
    install_fake_loader(monkeypatch)
    return make_plugin(state_dir=tmp_path / "plugin_data")


@pytest.fixture()
def run(plugin):
    def _run(message, sender_id="10001", as_admin=False):
        return dispatch(plugin, message, sender_id=sender_id, as_admin=as_admin)

    return _run


# --------------------------------------------------------------------------
# 面板结构
# --------------------------------------------------------------------------


def test_single_root_command_group():
    """面板里只应有一个顶层条目:mh 指令组。"""
    groups = root_groups()
    assert len(groups) == 1
    assert groups[0].group_name == "mh"
    assert groups[0].alias == {"怪物猎人"}


def test_no_bare_top_level_commands():
    """不允许有裸指令泄漏到顶层,否则面板又会变成一堆并列条目。"""
    leaked = [h.name for h in top_level_commands()]
    assert leaked == []


def test_every_handler_hangs_off_the_group():
    group = root_groups()[0]
    subs = [h for h in registry() if h.is_sub]
    assert len(subs) == len(EXPECTED_SUBCOMMANDS)
    assert all(
        h.filt.parent_command_names == group.complete_names() for h in subs
    )


# --------------------------------------------------------------------------
# 二级指令列表:名称 / 顺序 / 别名 / 中文介绍
# --------------------------------------------------------------------------


def test_subcommand_names_aliases_and_order():
    subs = root_groups()[0].sub_commands
    actual = [(c.command_name, c.alias) for c in subs]
    expected = [(name, aliases) for name, aliases, _ in EXPECTED_SUBCOMMANDS]
    assert actual == expected


def test_subcommands_are_backed_by_handlers():
    for _name, _alias, handler_name in EXPECTED_SUBCOMMANDS:
        handler = next(h for h in registry() if h.name == handler_name)
        assert handler.desc, f"{handler_name} 缺少 docstring(面板介绍来自它)"
        assert handler.is_sub


def test_update_is_admin_only():
    handler = next(h for h in registry() if h.name == "mh_update")
    assert handler.permission == ADMIN


# --------------------------------------------------------------------------
# 裸 /mh 渲染树形结构
# --------------------------------------------------------------------------


def test_bare_group_renders_tree(run):
    result = run("/mh")
    assert result.tree is not None
    assert result.handlers == []
    for name, _alias, _handler in EXPECTED_SUBCOMMANDS:
        assert name in result.tree
    # 每个子指令的中文介绍也会出现在树里
    for handler in registry():
        if handler.is_sub:
            assert handler.desc in result.tree


# --------------------------------------------------------------------------
# 路由与参数解析
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "handler", "needles"),
    [
        ("/mh 帮助", "mh_help", ["/mh 肉质"]),
        ("/mh 怪物列表", "mh_monsters", ["大型怪物"]),
        ("/mh 怪物列表 mhrise", "mh_monsters", ["怪物猎人:崛起"]),
        ("/mh 怪物 雌火龙", "mh_monster", ["雌火龙", "飞龙种", "怪物猎人:荒野"]),
        ("/mh 怪物 Rathian", "mh_monster", ["雌火龙"]),
        ("/mh 肉质 雌火龙", "mh_meat", ["雌火龙", "肉质表", "头部"]),
        ("/mh 肉质 陆之女王", "mh_meat", ["雌火龙"]),  # 通过别名命中
        ("/mh meat 雌火龙 mhwilds", "mh_meat", ["雌火龙"]),
        ("/怪物猎人 肉质 雌火龙", "mh_meat", ["雌火龙"]),  # 指令组别名
        ("!mh 肉质 雌火龙", "mh_meat", ["雌火龙"]),  # 另一个唤醒前缀
        ("/mh 弱点 雌火龙", "mh_weak", ["状态异常累积值"]),
        ("/mh 素材 雌火龙", "mh_rewards", ["剥取", "测试鳞"]),
        ("/mh 技能列表", "mh_skills", ["技能"]),
        ("/mh 技能 攻击力强化", "mh_skill", ["攻击力 +3"]),
        ("/mh 作品", "mh_games", ["已启用的作品"]),
        ("/mh 肉质", "mh_meat", ["缺少参数", "/mh 肉质 <名字> [作品]"]),
        ("/mh 怪物 不存在的怪", "mh_monster", ["未找到怪物"]),
    ],
)
def test_routing(run, message, handler, needles):
    result = run(message)
    assert result.handlers == [handler], message
    for needle in needles:
        assert needle in result.text, f"{message!r} 输出缺少 {needle!r}"


def test_unknown_subcommand_does_not_run_anything(run):
    """AstrBot 会把这条消息交给 LLM,但绝不能误触发别的子指令。"""
    result = run("/mh 乱写的子命令")
    assert result.handlers == []
    assert result.tree is None


def test_trailing_token_that_is_not_a_game_stays_in_the_name(run):
    """末位 token 不是已知作品标识时,应被当作名字的一部分(名字允许含空格)。"""
    result = run("/mh 肉质 雌火龙 火星")
    assert result.handlers == ["mh_meat"]
    assert "未找到怪物" in result.text
    assert "雌火龙 火星" in result.text


def test_disabled_game_is_reported(monkeypatch, tmp_path):
    install_fake_loader(monkeypatch)
    plugin = make_plugin(
        state_dir=tmp_path / "plugin_data",
        config={"default_game": "mhwilds", "enable_wilds": False},
    )
    result = dispatch(plugin, "/mh 肉质 雌火龙")
    assert result.handlers == ["mh_meat"]
    assert "作品不可用" in result.text


# --------------------------------------------------------------------------
# 权限与状态
# --------------------------------------------------------------------------


def test_update_blocked_for_non_admin(run):
    result = run("/mh 更新 mhwilds")
    assert result.handlers == ["mh_update"]
    assert result.blocked
    assert result.text == ""


def test_last_game_is_remembered_per_user(run):
    run("/mh 怪物列表 mhrise", sender_id="88888")
    again = run("/mh 怪物列表", sender_id="88888")
    assert "怪物猎人:崛起" in again.text
    # 其他用户不受影响
    other = run("/mh 怪物列表", sender_id="99999")
    assert "怪物猎人:崛起" not in other.text


# --------------------------------------------------------------------------
# 输出格式 (output_mode)
# --------------------------------------------------------------------------


def test_auto_mode_degrades_to_plain_text_without_renderer(run):
    """QQ 平台下 auto 会选 image，但测试替身没有 html_render，应回退纯文本。"""
    result = run("/mh 肉质 雌火龙")
    assert "肉质表" in result.text
    assert "头部" in result.text
    # 已降级：没有 markdown 的竖线 / 分隔行
    assert "|" not in result.text
    assert ":---" not in result.text


def test_markdown_mode_sends_raw_markdown(monkeypatch, tmp_path):
    install_fake_loader(monkeypatch)
    plugin = make_plugin(
        state_dir=tmp_path / "plugin_data", config={"output_mode": "markdown"}
    )
    result = dispatch(plugin, "/mh 肉质 雌火龙")
    assert "| 部位 |" in result.text
    assert ":---" in result.text


def test_text_mode_degrades_even_on_markdown_platform(monkeypatch, tmp_path):
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "text"})
    result = dispatch(plugin, "/mh 肉质 雌火龙", platform="telegram")
    assert "部位" in result.text
    assert "|" not in result.text


def test_auto_mode_uses_markdown_on_telegram(monkeypatch, tmp_path):
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "auto"})
    result = dispatch(plugin, "/mh 肉质 雌火龙", platform="telegram")
    assert "| 部位 |" in result.text


def test_image_mode_renders_card_via_html_render(monkeypatch, tmp_path):
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "image"})
    seen: dict = {}

    async def fake_render(tmpl, data, *args, **kwargs):
        seen["tmpl"] = tmpl
        seen["data"] = data
        return "https://example.com/card.png"

    plugin.html_render = fake_render
    result = dispatch(plugin, "/mh 肉质 雌火龙")
    assert result.text.startswith("[image] https://example.com/card.png")
    assert "<table>" in seen["data"]["content"]
    assert "<th" in seen["data"]["content"]
    assert "{{ content | safe }}" in seen["tmpl"]


def test_image_mode_passes_high_quality_render_options(monkeypatch, tmp_path):
    """AstrBot 默认 JPEG quality=40，文字发糊 —— 必须显式覆盖。"""
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "image"})
    seen: dict = {}

    async def fake_render(tmpl, data, *args, **kwargs):
        seen["options"] = kwargs.get("options")
        return "https://example.com/card.png"

    plugin.html_render = fake_render
    result = dispatch(plugin, "/mh 肉质 雌火龙")
    assert result.text.startswith("[image] ")
    assert seen["options"] == CARD_RENDER_OPTIONS
    assert seen["options"]["quality"] > 40


def test_image_mode_retries_without_options_when_signature_rejects_them(
    monkeypatch, tmp_path
):
    """老版本 AstrBot 的 html_render 没有 options 形参 —— 不能因此丢掉图片。"""
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "image"})
    calls: list = []

    async def legacy_render(tmpl, data):  # 没有 **kwargs
        calls.append(("legacy", len(data["content"])))
        return "https://example.com/legacy.png"

    plugin.html_render = legacy_render
    result = dispatch(plugin, "/mh 肉质 雌火龙")
    assert result.text == "[image] https://example.com/legacy.png"
    assert len(calls) == 1


def test_image_mode_retries_defaults_when_options_are_rejected(monkeypatch, tmp_path):
    """端点拒绝高质量参数时，应该用默认参数再试一次，而不是退回纯文本。"""
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "image"})
    attempts: list = []

    async def picky_render(tmpl, data, *args, **kwargs):
        attempts.append(kwargs.get("options"))
        if kwargs.get("options"):
            raise RuntimeError("unsupported option: quality")
        return "https://example.com/default.png"

    plugin.html_render = picky_render
    result = dispatch(plugin, "/mh 肉质 雌火龙")
    assert result.text == "[image] https://example.com/default.png"
    assert attempts == [CARD_RENDER_OPTIONS, None]


def test_image_mode_passes_the_monster_icon_into_the_card(monkeypatch, tmp_path):
    """只有 image 模式才贴怪物图：卡片数据里要带上该怪的 icon。"""
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "image"})
    seen: dict = {}

    async def fake_render(tmpl, data, *args, **kwargs):
        seen["data"] = data
        return "https://example.com/card.png"

    plugin.html_render = fake_render
    result = dispatch(plugin, "/mh 肉质 雌火龙")
    assert result.text.startswith("[image] ")
    assert 'src="https://example.com/icons/ci-huo-long.webp"' in seen["data"]["hero"]
    assert "onerror" in seen["data"]["hero"]


def test_image_mode_omits_the_hero_when_the_monster_has_no_icon(monkeypatch, tmp_path):
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "image"})
    seen: dict = {}

    async def fake_render(tmpl, data, *args, **kwargs):
        seen["data"] = data
        return "https://example.com/card.png"

    plugin.html_render = fake_render
    dispatch(plugin, "/mh 弱点 神龙")
    assert seen["data"]["hero"] == "", "没有图标就留空，由 .hero:empty 折叠掉"


def test_image_mode_omits_the_hero_for_non_monster_queries(monkeypatch, tmp_path):
    """作品 / 帮助 / 列表这类没有具体怪物的查询不带图标。"""
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "image"})
    seen: list = []

    async def fake_render(tmpl, data, *args, **kwargs):
        seen.append(data)
        return "https://example.com/card.png"

    plugin.html_render = fake_render
    dispatch(plugin, "/mh 作品")
    dispatch(plugin, "/mh 帮助")
    assert len(seen) == 2
    assert all(d["hero"] == "" for d in seen)


def test_image_mode_falls_back_when_renderer_raises(monkeypatch, tmp_path):
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "image"})

    async def boom(*args, **kwargs):
        raise RuntimeError("playwright not installed")

    plugin.html_render = boom
    result = dispatch(plugin, "/mh 肉质 雌火龙")
    assert "肉质表" in result.text
    assert "|" not in result.text


def test_text_and_markdown_modes_never_carry_the_icon(monkeypatch, tmp_path):
    """文本 / markdown 输出保持原样 —— 不出现图标、也不触发渲染。"""
    install_fake_loader(monkeypatch)
    calls: list = []

    async def fake_render(tmpl, data, *args, **kwargs):  # pragma: no cover - 不该被调用
        calls.append(data)
        return "https://example.com/card.png"

    for mode in ("text", "markdown"):
        plugin = make_plugin(state_dir=tmp_path / f"state_{mode}", config={"output_mode": mode})
        plugin.html_render = fake_render
        result = dispatch(plugin, "/mh 肉质 雌火龙")
        assert "https://example.com/icons" not in result.text
        assert "<img" not in result.text
        assert "部位" in result.text
    assert calls == [], "text / markdown 模式不应该走文转图"


def test_errors_stay_plain_text_even_in_image_mode(monkeypatch, tmp_path):
    install_fake_loader(monkeypatch)
    plugin = make_plugin(state_dir=tmp_path / "plugin_data", config={"output_mode": "image"})
    calls: list = []

    async def fake_render(tmpl, data, *args, **kwargs):  # pragma: no cover - must not run
        calls.append(data)
        return "https://example.com/card.png"

    plugin.html_render = fake_render
    result = dispatch(plugin, "/mh 怪物 zzz不存在")
    assert "未找到怪物" in result.text
    assert calls == [], "错误提示不应该触发文转图"


# --------------------------------------------------------------------------
# 参数剥离
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("/mh 肉质 雌火龙", ["雌火龙"]),
        ("mh 肉质 雌火龙", ["雌火龙"]),  # 私聊/@ 唤醒时没有前缀
        ("/mh   肉质    雌火龙   ", ["雌火龙"]),
        ("/mh 怪物 火 龙", ["火", "龙"]),
        ("/mh 作品", []),
        ("/怪物猎人 技能列表 mhrise", ["mhrise"]),
    ],
)
def test_arg_tokens(message, expected):
    from ._astrbot_fake import _FakeEvent

    assert MOD.MHHelperPlugin._arg_tokens(_FakeEvent(message)) == expected
