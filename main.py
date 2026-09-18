"""AstrBot plugin entry: Monster Hunter information lookup (MHWorld / MHRise / MHWilds).

The whole plugin exposes exactly **one** AstrBot command (group):

    /mh <子命令> [名字] [作品]

Registering a single command group instead of ~20 flat commands is what makes
the WebUI 「指令管理」 page readable: it shows one collapsible `mh` row whose
badge counts the sub-commands, and expanding it lists the second-level
sub-commands with their descriptions (taken from each handler's docstring).

    /mh 帮助              查看完整帮助            (help)
    /mh 怪物 <名字> [作品]  属性弱点 / 肉质表 / 状态异常 (monster)
    /mh 技能 <名字> [作品]  技能各等级效果          (skill)
    /mh 作品              列出已启用作品            (games)
    /mh 更新 [作品]         管理员：在线刷新数据      (update)

`基础信息 / 肉质 / 弱点` 已合并成 `怪物` 一条，按「怪物名 → 属性弱点 → 肉质表 → 异常累积」的顺序输出；图片模式下卡片顶部还会居中显示怪物图标。

括号里是等价别名：`/mh meat Rathian` == `/mh 怪物 Rathian`（`肉质`/`弱点`/`属性`
等老名字都保留为别名，习惯输入照旧可用，返回的都是同一份合并报告）。

全局只有**一份**「当前作品」（存放在配置项 `default_game`），所有命令都用它；
    管理员用 `/mh 作品 <作品名>` 切换（会写回配置并保存，重启不丢），普通命令
    **不再接受 [作品] 后缀**。
作品标识支持：mhworld / world / 世界、mhrise / rise / 崛起、mhwilds / wilds / 荒野。

用户直接发送裸 `/mh`（不带子命令）时，AstrBot 会自动渲染出本指令组的树形
结构（含子指令描述），因此无需再额外注册一个「帮助」根命令。

输出格式由配置项 `output_mode` 决定（见 core/render.py）：

* `auto`（默认）—— 按平台自动选：QQ 全系走 `image`，Telegram/飞书等走 `markdown`
* `markdown` —— 直接发 markdown 文本
* `image` —— 用 AstrBot 的「文转图」把结果渲染成图片卡片
* `text` —— 退化成空格对齐的纯文本

格式化层（core/formatter.py）统一产出 markdown，上面几种只是「怎么送出去」。
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
import time
from collections.abc import Mapping
from typing import Any

# ---------------------------------------------------------------------------
# Import bootstrap — why this is not just `sys.path.insert`
# ---------------------------------------------------------------------------
# AstrBot loads a plugin as `data.plugins.<目录名>.main` and, when reloading or
# updating it, purges `sys.modules` entries whose name starts with
# `data.plugins.<目录名>` (see `PluginManager._purge_modules` in
# `astrbot/core/star/star_manager.py`, and the `path = "data.plugins."` +
# `root_dir_name` construction in `load()`).
#
# Our own subpackages are imported by their *bare top-level* names
# (`core.formatter`, `scraper.common`), which that prefix never matches, so a
# reload leaves the previous version's modules alive in memory. Two real
# consequences, both seen in the wild:
#
#   1. after an in-place update the new `main.py` keeps binding the *old*
#      submodules, and fails with import errors that do not match the files on
#      disk — e.g. `cannot import name 'light_table' from 'core.formatter'`
#      even though the file on disk does define it;
#   2. `core` is generic enough that another plugin can claim the name first,
#      in which case we would silently import somebody else's code.
#
# Both are fixed by evicting the affected entries before we import anything.
# `main.py` itself is always re-executed on reload (AstrBot does purge its own
# module), so this runs exactly when it is needed.

_PKG_DIR = Path(__file__).resolve().parent

#: 插件自己用绝对名导入的顶层包。新增子包时**必须**同步加进来，否则它不会
#: 在插件重载时被清掉。
_INTERNAL_PACKAGES: tuple[str, ...] = ("core", "scraper")

_boot_log = logging.getLogger("astrbot-mhhelper")


def _module_origin(module: Any) -> Path | None:
    """``Path(module.__file__).resolve()``, or None when unavailable."""
    path = getattr(module, "__file__", None)
    if not path:
        return None
    try:
        return Path(path).resolve()
    except OSError:  # pragma: no cover - 病态路径
        return None


def _is_inside_plugin_dir(path: Path) -> bool:
    return path == _PKG_DIR or _PKG_DIR in path.parents


def _stale_module_names(modules: Mapping[str, Any]) -> list[str]:
    """Entries of ``modules`` that must be dropped before importing our code.

    Anything whose *top-level* name is one of :data:`_INTERNAL_PACKAGES` — the
    package itself, or any submodule of it. Such an entry is either our own code
    left behind by a previous version, or another plugin squatting the name;
    both must go so that `import core.x` resolves to the files on disk.

    Deliberately name-based and narrow: the plugin directory also holds things
    like `tests/`, and a path-based rule would evict those too. Pure function, so
    it can be tested without touching the real ``sys.modules``.
    """
    return [
        name
        for name, module in list(modules.items())
        if module is not None and name.split(".", 1)[0] in _INTERNAL_PACKAGES
    ]


def _evict_stale_modules() -> list[str]:
    """Drop the entries reported by :func:`_stale_module_names`."""
    names = _stale_module_names(sys.modules)
    for name in names:
        module = sys.modules.get(name)
        origin = _module_origin(module) if module is not None else None
        if origin is not None and not _is_inside_plugin_dir(origin):
            _boot_log.warning(
                "[astrbot_plugin_mhhelper] module %r was claimed by %s; dropping it "
                "so our own copy wins",
                name,
                origin,
            )
        sys.modules.pop(name, None)
    return names


_EVICTED_MODULES: list[str] = _evict_stale_modules()

# 插件目录本身也要在 sys.path 上：我们用绝对名 `core.*` 导入子包。
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

if _EVICTED_MODULES:
    _boot_log.info(
        "[astrbot_plugin_mhhelper] dropped %d stale module(s) left over from a "
        "previous load: %s",
        len(_EVICTED_MODULES),
        ", ".join(sorted(_EVICTED_MODULES)),
    )

from astrbot.api.event import AstrMessageEvent, filter  # noqa: E402
from astrbot.api.star import Star, register  # noqa: E402
from astrbot.core.config.astrbot_config import AstrBotConfig  # type: ignore  # noqa: E402

from core.data_loader import GAMES, GAME_LABELS, get_loader  # noqa: E402
from core.errors import (  # noqa: E402
    DataNotLoaded,
    GameDisabled,
    InvalidGame,
    MonsterNotFound,
    SkillNotFound,
)
from core.formatter import (  # noqa: E402
    render_error,
    render_games,
    render_help,
    render_monster_report,
    render_skill,
    render_switch_result,
    render_update_result,
)
from core.monster_index import get_monster_index  # noqa: E402
from core.render import (  # noqa: E402
    CARD_RENDER_OPTIONS,
    CARD_TEMPLATE,
    card_hero,
    markdown_to_html,
    markdown_to_plaintext,
    resolve_mode,
)
from core.skill_index import get_skill_index  # noqa: E402

log = logging.getLogger("astrbot-mhhelper")

PLUGIN_NAME = "astrbot_plugin_mhhelper"
PLUGIN_VERSION = "0.3.8"

#: 指令组名与别名 —— 面板里显示的顶层条目就是它。
GROUP_NAME = "mh"
GROUP_ALIASES: set[str] = {"怪物猎人"}
_GROUP_TOKENS: frozenset[str] = frozenset(
    {GROUP_NAME.lower(), *(a.lower() for a in GROUP_ALIASES)}
)

#: 唤醒前缀之外可能残留的前导符号（用户 `@bot /mh …` 时 AstrBot 不会剥离前缀）。
_LEADING_JUNK = "/!！~.。、"

GAME_ALIASES: dict[str, str] = {
    "world": "mhworld",
    "mhworld": "mhworld",
    "iceborne": "mhworld",
    "rise": "mhrise",
    "mhrise": "mhrise",
    "sunbreak": "mhrise",
    "wilds": "mhwilds",
    "mhwilds": "mhwilds",
    "荒野": "mhwilds",
    "崛起": "mhrise",
    "世界": "mhworld",
    "曙光": "mhrise",
}

#: 作品 → 控制其可用性的配置项。
_ENABLE_CONFIG_KEY: dict[str, str] = {
    "mhworld": "enable_world",
    "mhrise": "enable_rise",
    "mhwilds": "enable_wilds",
}

#: 缺少「名字」参数时提示的用法片段，键为 _dispatch 的内部子命令标识。
USAGE: dict[str, str] = {
    "monster": "怪物 <名字>",
    "skill": "技能 <名字>",
}


def _resolve_game(token: str | None) -> str:
    """Return canonical game key for a user-provided token."""
    if not token:
        return "mhwilds"
    key = token.strip().lower().replace(" ", "")
    return GAME_ALIASES.get(key, key)


@register(PLUGIN_NAME, "Noplch0", "怪物猎人信息查询 (MHWorld / MHRise / MHWilds)", PLUGIN_VERSION)
class MHHelperPlugin(Star):
    def __init__(self, context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or self._default_config()
        self._init_indexes()

    # ------------------- lifecycle -------------------

    async def initialize(self) -> None:
        self._init_indexes()
        log.info("[%s] loaded.", PLUGIN_NAME)

    # ------------------- internal helpers -------------------

    def _default_config(self) -> dict[str, Any]:
        return {
            "default_game": "mhwilds",
            "enable_world": True,
            "enable_rise": True,
            "enable_wilds": True,
            "output_mode": "auto",
            "proxy": "",
            "max_rows_per_message": 30,
            "allow_runtime_update": True,
        }

    def _init_indexes(self) -> None:
        loader = get_loader()
        loader.invalidate()
        enabled = {
            game: bool(self.config.get(key, True))
            for game, key in _ENABLE_CONFIG_KEY.items()
        }
        self._enabled_games = {g for g, on in enabled.items() if on}
        self._monster_idx = get_monster_index()
        self._monster_idx.configure(enabled)
        self._skill_idx = get_skill_index()
        self._skill_idx.configure(enabled)
        for g in GAMES:
            try:
                self._monster_idx.reload(g)
                self._skill_idx.reload(g)
            except DataNotLoaded:
                log.warning("[%s] data missing for %s", PLUGIN_NAME, g)

    def _current_game(self) -> str:
        """当前生效的作品 —— 全局只有一份，就是配置项 ``default_game``。

        管理员用 `/mh 作品 <作品名>` 切换（写回配置并保存，重启不丢）。
        配置里的作品被禁用或不存在时，退回第一个启用的作品，保证总有数据可查。
        """
        configured = str(self.config.get("default_game", "") or "")
        if configured in self._enabled_games:
            return configured
        for game in GAMES:  # 固定顺序，保证可复现
            if game in self._enabled_games:
                log.info(
                    "[%s] default_game=%s 不可用，回退到 %s",
                    PLUGIN_NAME, configured, game,
                )
                return game
        return configured or "mhwilds"

    def _set_current_game(self, game: str) -> None:
        """切换全局作品并写回配置项 ``default_game``（重启后仍生效）。"""
        self.config["default_game"] = game
        # AstrBotConfig 有 save_config()；测试替身是普通 dict，没有就跳过。
        save = getattr(self.config, "save_config", None)
        if callable(save):
            save()

    @staticmethod
    def _is_admin(event: AstrMessageEvent) -> bool:
        """运行时判断管理员 —— `/mh 作品 <作品名>` 只对管理员开放。"""
        try:
            return bool(event.is_admin())
        except Exception:  # noqa: BLE001 - 适配器没实现就按非管理员处理
            return False

    @staticmethod
    def _arg_tokens(event: AstrMessageEvent) -> list[str]:
        """Return the argument tokens a sub-command handler should parse.

        AstrBot strips the wake prefix but leaves the command itself in
        `event.message_str`, so `/mh 肉质 火龙` reaches the handler as
        `"mh 肉质 火龙"`. The first token is the group name and the second is
        the sub-command; everything after those is the actual argument list.
        """
        text = re.sub(r"\s+", " ", (event.message_str or "").strip())
        text = text.lstrip(_LEADING_JUNK).strip()
        tokens = [t for t in text.split(" ") if t]
        # 找到指令组名（mh / 别名），其后第一个 token 才是子指令名。
        for i, tok in enumerate(tokens):
            if tok.lower() in _GROUP_TOKENS:
                return tokens[i + 2:]
        # 理论上不会被走到；退化为「跳过子指令名」。
        return tokens[1:]

    def _split_args(self, event: AstrMessageEvent, sub: str) -> tuple[str, list[str]]:
        """返回（当前作品，名字参数）。

        v0.3.8 起**所有命令都不再接受 [作品] 后缀**：全局只有一份「当前作品」，
        由管理员用 `/mh 作品 <作品名>` 切换，普通命令一律使用它。
        """
        return self._current_game(), self._arg_tokens(event)

    # ------------------- output delivery -------------------
    # 格式化层统一产出 markdown，这里按平台决定怎么把它送到用户面前：
    #   markdown → 原样发 md（Telegram / 飞书 / Discord 等会原生渲染）
    #   image    → 用 AstrBot 的「文转图」渲染成图片卡片（QQ 个人号唯一可选）
    #   text     → 退化成空格对齐的纯文本
    # 任何一步失败都 gracefully 回退到纯文本，绝不让格式化把查询搞挂。

    @staticmethod
    def _platform_name(event: AstrMessageEvent) -> str:
        for attr in ("get_platform_name", "get_platform_id"):
            getter = getattr(event, attr, None)
            if callable(getter):
                try:
                    value = getter()
                except Exception:  # noqa: BLE001
                    value = None
                if value:
                    return str(value)
        # 退路：unified_msg_origin 形如 "aiocqhttp:GroupMessage:123456"
        origin = getattr(event, "unified_msg_origin", "") or ""
        return str(origin).split(":", 1)[0]

    def _text_result(self, event: AstrMessageEvent, md: str):
        """Deliver as plain text — markdown is degraded to aligned columns."""
        return event.plain_result(markdown_to_plaintext(md))

    async def _image_result(
        self,
        event: AstrMessageEvent,
        md: str,
        monster: dict[str, Any] | None = None,
    ):
        """Render markdown to an image via AstrBot's 文转图; None if unusable."""
        render = getattr(self, "html_render", None)
        if not callable(render):
            return None
        url = await self._render_card(
            render, markdown_to_html(md), card_hero(monster)
        )
        if not url:
            return None
        try:
            return event.image_result(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s] image_result 失败: %s", PLUGIN_NAME, exc)
            return None

    async def _render_card(self, render, html_body: str, hero: str = "") -> str | None:
        """渲染卡片；先带高质量参数，失败再用 AstrBot 默认参数重试一次。

        AstrBot 默认是 JPEG ``quality=40``（``NetworkRenderStrategy`` 里写死的），
        文字会发糊，所以先用 :data:`CARD_RENDER_OPTIONS` 覆盖。两种失败要区分对待：

        * 老版本 AstrBot 的 ``html_render`` 没有 ``options`` 形参 → ``TypeError``，
          必须退到"不传 options"再试，否则会白白丢掉图片模式；
        * 参数被 t2i 端点拒绝 / 网络抖动 → 也用默认参数再试一次。

        两次都不成才返回 ``None``，由调用方回退纯文本。

        ``hero`` 是卡片顶部居中的怪物图标（只有 image 模式才有），空串表示没有。
        """
        data = {"content": html_body, "hero": hero}
        for options in (CARD_RENDER_OPTIONS, None):
            try:
                if options is None:
                    url = await render(CARD_TEMPLATE, data)
                else:
                    url = await render(CARD_TEMPLATE, data, options=options)
            except TypeError as exc:
                log.info("[%s] 文转图不接受 options，改用默认参数: %s", PLUGIN_NAME, exc)
                continue
            except Exception as exc:  # noqa: BLE001
                log.warning("[%s] 文转图失败（options=%s），重试默认参数: %s",
                            PLUGIN_NAME, options, exc)
                continue
            if url:
                return str(url)
        return None

    async def _emit(
        self,
        event: AstrMessageEvent,
        md: str,
        monster: dict[str, Any] | None = None,
    ):
        """Deliver formatter markdown according to the configured output mode.

        ``monster`` 只在 image 模式下用得上（卡片顶部的图标）—— 文本 / markdown
        输出完全不受它影响，所以不传也完全正常。
        """
        mode = resolve_mode(
            self.config.get("output_mode", "auto"), self._platform_name(event)
        )
        if mode == "markdown":
            return event.plain_result(md)
        if mode == "image":
            result = await self._image_result(event, md, monster)
            if result is not None:
                return result
        return self._text_result(event, md)

    # ------------------- shared dispatch -------------------

    async def _dispatch(self, event: AstrMessageEvent, sub: str):
        """Single dispatch used by every sub-command handler."""
        game, name_args = self._split_args(event, sub)

        if sub == "help":
            yield await self._emit(event, render_help())
            return

        if game not in GAMES:
            yield self._text_result(
                event,
                render_error("未知作品", f"未识别的作品标识: {game}", list(GAME_LABELS)),
            )
            return
        if game not in self._enabled_games:
            # 只有「一个启用的作品都没有」才会走到这里（_current_game 会自动回退）。
            yield self._text_result(
                event,
                render_error(
                    "作品不可用",
                    f"{GAME_LABELS.get(game, game)} 已在插件配置中禁用。",
                ),
            )
            return

        max_rows = self.config.get("max_rows_per_message", 30)

        try:
            if sub == "games":
                games = self._monster_idx.list_games()
                if not name_args:
                    yield await self._emit(
                        event, render_games(games, current=self._current_game())
                    )
                    return
                # 带参数 = 切换全局作品。**仅管理员**；这个用法不写进帮助，
                # 普通用户在指令列表里看不到它。
                if not self._is_admin(event):
                    yield self._text_result(
                        event,
                        render_error("需要管理员权限", "切换作品是管理员操作。"),
                    )
                    return
                target = _resolve_game(name_args[0])
                if target not in GAMES:
                    known = " / ".join(GAME_LABELS.get(g, g) for g in games) or "无"
                    yield self._text_result(
                        event,
                        render_error(
                            "未知作品",
                            f"无法识别的作品: {name_args[0]}",
                            [f"可用作品: {known}"],
                        ),
                    )
                    return
                if target not in self._enabled_games:
                    yield self._text_result(
                        event,
                        render_error(
                            "作品不可用",
                            f"{GAME_LABELS.get(target, target)} 未启用，"
                            "请先在插件配置里打开。",
                        ),
                    )
                    return
                previous = self._current_game()
                self._set_current_game(target)
                yield self._text_result(
                    event, render_switch_result(target, previous)
                )
                return
            if sub in {"monster", "skill"} and not name_args:
                yield self._text_result(
                    event,
                    render_error("缺少参数", f"用法: /mh {USAGE[sub]}"),
                )
                return
            if sub == "monster":
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(name_args), game)
                # 基础信息 / 肉质 / 弱点合并成一份报告；怪物也一并交给投递层，
                # 图片模式下卡片顶部的图标就来自它（文本模式用不到）。
                yield await self._emit(
                    event,
                    render_monster_report(monster, resolved_game, max_rows),
                    monster,
                )
                return
            if sub == "skill":
                _, skill, resolved_game = self._skill_idx.lookup(" ".join(name_args), game)
                # 技能效果**永远发文本**：只有几行字，转图只会更难读，所以这里
                # 故意不走 _emit —— 无论 output_mode 选什么都不渲染。
                yield self._text_result(event, render_skill(skill, resolved_game))
                return
            if sub == "update":
                async for r in self._cmd_update(event, game):
                    yield r
                return
            yield await self._emit(event, render_help())
        except MonsterNotFound as exc:
            yield self._text_result(
                event,
                render_error(
                    "未找到怪物",
                    f"在 {GAME_LABELS.get(game, game)} 中找不到: {exc.query}",
                    exc.suggestions,
                ),
            )
        except SkillNotFound as exc:
            yield self._text_result(
                event,
                render_error(
                    "未找到技能",
                    f"在 {GAME_LABELS.get(game, game)} 中找不到: {exc.query}",
                    exc.suggestions,
                ),
            )
        except DataNotLoaded as exc:
            yield self._text_result(
                event,
                render_error(
                    "数据未加载",
                    f"该作品的数据未就绪。请联系管理员执行 /mh 更新 {exc.game} 或重新安装插件。",
                ),
            )
        except (InvalidGame, GameDisabled) as exc:
            yield self._text_result(event, render_error("作品不可用", str(exc)))
        except Exception as exc:  # noqa: BLE001
            log.exception("Handler error: %s", exc)
            yield self._text_result(event, render_error("内部错误", str(exc)))

    async def _cmd_update(self, event: AstrMessageEvent, game: str):
        if not self.config.get("allow_runtime_update", True):
            yield self._text_result(
                event,
                render_error("已禁用", "管理员已禁用在线刷新。请让管理员重新安装插件。"),
            )
            return
        yield event.plain_result(f"⏳ 正在从 kiranico 拉取 {GAME_LABELS.get(game, game)} 数据…")
        try:
            from scraper.common import SCRAPERS
            from scraper.run_update import refresh_game
        except ImportError as e:
            yield self._text_result(event, render_error("抓取模块不可用", str(e)))
            return
        if game not in SCRAPERS:
            yield self._text_result(event, render_error("未知作品", game))
            return
        t0 = time.time()
        monsters, skills = await refresh_game(
            game,
            proxy=self.config.get("proxy") or None,
            concurrency=4,
            delay=0.1,
            only=None,
        )
        self._init_indexes()
        yield await self._emit(event, render_update_result(game, monsters, skills, time.time() - t0))

    # ------------------- command group -------------------
    # 「指令管理」面板会把下面这一整块收拢成一个可展开的 `mh` 行；
    # 每个子命令的 docstring 就是面板/树形结构里显示的中文说明。

    @filter.command_group(GROUP_NAME, alias=GROUP_ALIASES)
    def mh(self):
        """怪物猎人查询：怪物（肉质 / 弱点 / 异常）/ 技能 / 作品"""

    @mh.command("帮助", alias={"help", "用法"})
    async def mh_help(self, event: AstrMessageEvent):
        """查看完整帮助：全部子命令与用法示例"""
        async for r in self._dispatch(event, "help"):
            yield r

    # 基础信息 / 肉质 / 弱点 合并成这一条 —— 老的 肉质 / 弱点 名字保留为别名，
    # 习惯性输入仍然可用，返回的都是同一份合并报告。
    @mh.command(
        "怪物",
        alias={"monster", "info", "肉质", "肉", "meat", "弱点", "属性", "weak"},
    )
    async def mh_monster(self, event: AstrMessageEvent):
        """查询怪物：属性弱点 / 肉质表 / 异常累积（用法：/mh 怪物 <名字>）"""
        async for r in self._dispatch(event, "monster"):
            yield r

    @mh.command("技能", alias={"skill"})
    async def mh_skill(self, event: AstrMessageEvent):
        """查看技能各等级效果（用法：/mh 技能 <名字>）"""
        async for r in self._dispatch(event, "skill"):
            yield r

    @mh.command("作品", alias={"games", "game"})
    async def mh_games(self, event: AstrMessageEvent):
        """列出已启用、可查询的作品"""
        async for r in self._dispatch(event, "games"):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @mh.command("更新", alias={"update", "刷新"})
    async def mh_update(self, event: AstrMessageEvent):
        """管理员：从 kiranico 在线刷新当前作品的数据（用法：/mh 更新）"""
        async for r in self._dispatch(event, "update"):
            yield r
