"""AstrBot plugin entry: Monster Hunter information lookup (MHWorld / MHRise / MHWilds).

The whole plugin exposes exactly **one** AstrBot command (group):

    /mh <子命令> [名字] [作品]

Registering a single command group instead of ~20 flat commands is what makes
the WebUI 「指令管理」 page readable: it shows one collapsible `mh` row whose
badge counts the sub-commands, and expanding it lists the second-level
sub-commands with their descriptions (taken from each handler's docstring).

    /mh 帮助              查看完整帮助            (help)
    /mh 怪物列表 [作品]     列出该作大型怪物         (monsters)
    /mh 怪物 <名字> [作品]  怪物基础信息            (monster)
    /mh 肉质 <名字> [作品]  肉质表                  (meat)
    /mh 弱点 <名字> [作品]  属性弱点与状态异常       (weak)
    /mh 素材 <名字> [作品]  剥取 / 破坏 / 目标报酬   (rewards)
    /mh 技能列表 [作品]     列出该作技能            (skills)
    /mh 技能 <名字> [作品]  技能各等级效果          (skill)
    /mh 作品              列出已启用作品            (games)
    /mh 更新 [作品]         管理员：在线刷新数据      (update)

括号里是等价别名：`/mh meat Rathian` == `/mh 肉质 Rathian`。

`作品` 可省略；省略时按「该用户上次使用 → 配置 default_game」解析。
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

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

# Make sibling subpackages importable when AstrBot loads this file as a module.
# AstrBot v4 imports the plugin via `__import__("astrbot_plugin_mhhelper.main", ...)`,
# which means the plugin's own directory is not on sys.path — so `from core import …`
# fails with ModuleNotFoundError. Prepending __file__'s parent fixes that, and
# is a no-op when AstrBot already placed the dir on sys.path.
_PKG_DIR = Path(__file__).resolve().parent
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

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
    render_meat,
    render_monster_info,
    render_monster_list,
    render_rewards,
    render_skill,
    render_skill_list,
    render_update_result,
    render_weak,
)
from core.monster_index import get_monster_index  # noqa: E402
from core.render import (  # noqa: E402
    CARD_TEMPLATE,
    markdown_to_html,
    markdown_to_plaintext,
    resolve_mode,
)
from core.skill_index import get_skill_index  # noqa: E402

log = logging.getLogger("astrbot-mhhelper")

PLUGIN_NAME = "astrbot_plugin_mhhelper"
PLUGIN_VERSION = "0.3.1"

#: 运行期状态：每个用户上次查询的作品。
STATE_FILENAME = "user_last_game.json"

#: 旧版（<= v0.3.0）把状态写在插件目录下的这个文件夹里。新版按官方规范
#: 改写到 AstrBot 的 `data/plugin_data/<插件名>/`，并在首次保存时把旧文件
#: 迁移过去后再删除（见 `_drop_legacy_state`）。这里的常量仍要保留：既是
#: 迁移来源，也是官方目录完全不可用时的最后退路。
LEGACY_STATE_DIRNAME = "plugin_data"

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

#: 只接受「作品」一个参数的子命令（没有「名字」参数）。
_GAME_ONLY_SUBS: frozenset[str] = frozenset({"monsters", "skills", "games", "update"})

#: 作品 → 控制其可用性的配置项。
_ENABLE_CONFIG_KEY: dict[str, str] = {
    "mhworld": "enable_world",
    "mhrise": "enable_rise",
    "mhwilds": "enable_wilds",
}

#: 缺少「名字」参数时提示的用法片段，键为 _dispatch 的内部子命令标识。
USAGE: dict[str, str] = {
    "monster": "怪物 <名字> [作品]",
    "meat": "肉质 <名字> [作品]",
    "weak": "弱点 <名字> [作品]",
    "rewards": "素材 <名字> [作品]",
    "skill": "技能 <名字> [作品]",
}


def _resolve_game(token: str | None) -> str:
    """Return canonical game key for a user-provided token."""
    if not token:
        return "mhwilds"
    key = token.strip().lower().replace(" ", "")
    return GAME_ALIASES.get(key, key)


def _looks_like_game(token: str) -> bool:
    return token in GAMES or token in GAME_ALIASES


@register(PLUGIN_NAME, "Noplch0", "怪物猎人信息查询 (MHWorld / MHRise / MHWilds)", PLUGIN_VERSION)
class MHHelperPlugin(Star):
    def __init__(self, context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or self._default_config()
        #: 插件自身目录 —— 只在「官方数据目录不可用」时才用来落盘（见 _plugin_state_dir）。
        self._data_root = Path(__file__).resolve().parent
        self._state_path = self._plugin_state_dir() / STATE_FILENAME
        self._user_game_cache: dict[str, str] = self._load_user_state()
        self._init_indexes()

    # ------------------- lifecycle -------------------

    async def initialize(self) -> None:
        self._init_indexes()
        log.info("[%s] loaded.", PLUGIN_NAME)

    async def terminate(self) -> None:
        self._save_user_state()

    # ------------------- persistent state -------------------
    # AstrBot 官方规范：持久化数据必须放在 AstrBot 的 `data/` 目录下
    # （即 `data/plugin_data/<插件名>/`），**不能**放在插件自身目录里 ——
    # 插件目录在更新 / 重装时会被整体替换，放在里面的数据会一起丢。
    # https://docs.astrbot.app/dev/star/guides/storage.html
    #
    # 解析顺序：官方 API → 从插件路径反推 → 退回插件目录（保命用，会告警）。

    @staticmethod
    def _plugin_id() -> str:
        """插件名，用作 `data/plugin_data/` 下的子目录名。"""
        return PLUGIN_NAME

    def _official_state_dir(self) -> Path | None:
        """``Path(get_astrbot_data_path()) / "plugin_data" / <插件名>``。

        官方 API（AstrBot >= 4.9.2 提供 ``self.name``；``astrbot_path`` 更早
        就有）。不可用时返回 ``None``，交给下一级解析。
        """
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path

            root = Path(get_astrbot_data_path())
        except Exception:  # noqa: BLE001 - 老版本 AstrBot 没有这个模块
            return None
        return root / "plugin_data" / self._plugin_id()

    def _derived_state_dir(self) -> Path | None:
        """退路：插件装在 ``<root>/data/plugins/<插件名>``，据此反推官方目录。

        只在上面那个官方 API 不可用时（很老的 AstrBot）才会用到。目录结构
        不符合预期时返回 ``None``，避免在莫名其妙的路径下建目录。
        """
        plugins = self._data_root.parent
        data = plugins.parent
        if plugins.name != "plugins" or data.name != "data":
            return None
        return data / "plugin_data" / self._plugin_id()

    def _legacy_state_path(self) -> Path:
        """旧版位置：插件目录下的 ``plugin_data/user_last_game.json``。"""
        return self._data_root / LEGACY_STATE_DIRNAME / STATE_FILENAME

    def _plugin_state_dir(self) -> Path:
        """解析状态目录；逐级降级，保证插件在任何部署形态下都能启动。"""
        for resolver in (self._official_state_dir, self._derived_state_dir):
            try:
                candidate = resolver()
            except Exception:  # noqa: BLE001
                candidate = None
            if candidate is None:
                continue
            try:
                candidate.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log.warning("[%s] 无法创建数据目录 %s: %s", PLUGIN_NAME, candidate, exc)
                continue
            return candidate
        # 最后退路：官方目录实在不可用时退回插件目录。宁可位置不标准，
        # 也好过因为盘写不进去而让整个插件加载失败。
        fallback = self._data_root / LEGACY_STATE_DIRNAME
        fallback.mkdir(parents=True, exist_ok=True)
        log.warning(
            "[%s] 官方数据目录不可用，状态将写在插件目录内（更新插件会丢）: %s",
            PLUGIN_NAME,
            fallback,
        )
        return fallback

    def _state_candidates(self) -> list[Path]:
        """按优先级列出可能存有状态的文件，用于迁移期读取旧数据。"""
        paths = [self._state_path]
        legacy = self._legacy_state_path()
        if legacy != self._state_path:
            paths.append(legacy)
        return paths

    def _load_user_state(self) -> dict[str, str]:
        for path in self._state_candidates():
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("[%s] 状态文件无法解析，已忽略 %s: %s", PLUGIN_NAME, path, exc)
                continue
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        return {}

    def _save_user_state(self) -> None:
        try:
            self._state_path.write_text(
                json.dumps(self._user_game_cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to save user state: %s", exc)
            return
        self._drop_legacy_state()

    def _drop_legacy_state(self) -> None:
        """迁移成功后删掉插件目录里的旧状态文件，避免两份数据互相打架。

        只有在确实写到别的位置（即 ``_state_path`` 不是旧路径）时才清理。
        """
        legacy = self._legacy_state_path()
        if legacy == self._state_path or not legacy.is_file():
            return
        try:
            legacy.unlink()
            legacy.parent.rmdir()  # 目录空了就一并收拾干净
        except OSError:
            pass  # 里面还有别的东西，留着即可

    # ------------------- internal helpers -------------------

    def _default_config(self) -> dict[str, Any]:
        return {
            "default_game": "mhwilds",
            "enable_world": True,
            "enable_rise": True,
            "enable_wilds": True,
            "with_icon": False,
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

    def _user_default_game(self, event: AstrMessageEvent) -> str:
        uid = self._event_user_id(event)
        if uid and uid in self._user_game_cache:
            return self._user_game_cache[uid]
        return self.config.get("default_game", "mhwilds")

    def _remember_game(self, event: AstrMessageEvent, game: str) -> None:
        uid = self._event_user_id(event)
        if uid:
            self._user_game_cache[uid] = game

    @staticmethod
    def _event_user_id(event: AstrMessageEvent) -> str:
        try:
            return str(event.get_sender_id())
        except Exception:
            return ""

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
        """Resolve `[名字…] [作品]` into (game, name_tokens)."""
        parts = self._arg_tokens(event)
        game_hint = None
        # 最后一个 token 可能是作品标识
        if parts and _looks_like_game(parts[-1]):
            game_hint = _resolve_game(parts[-1])
            parts = parts[:-1]
        elif sub in _GAME_ONLY_SUBS and parts:
            # 这些子命令只接受一个可选的作品标识
            only = _resolve_game(parts[0])
            if only in GAMES:
                game_hint = only
                parts = parts[1:]
        game = game_hint or self._user_default_game(event)
        return game, parts

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

    async def _image_result(self, event: AstrMessageEvent, md: str):
        """Render markdown to an image via AstrBot's 文转图; None if unusable."""
        render = getattr(self, "html_render", None)
        if not callable(render):
            return None
        try:
            url = await render(CARD_TEMPLATE, {"content": markdown_to_html(md)})
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s] 文转图失败，回退纯文本: %s", PLUGIN_NAME, exc)
            return None
        if not url:
            return None
        try:
            return event.image_result(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s] image_result 失败: %s", PLUGIN_NAME, exc)
            return None

    async def _emit(self, event: AstrMessageEvent, md: str):
        """Deliver formatter markdown according to the configured output mode."""
        mode = resolve_mode(
            self.config.get("output_mode", "auto"), self._platform_name(event)
        )
        if mode == "markdown":
            return event.plain_result(md)
        if mode == "image":
            result = await self._image_result(event, md)
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
            yield self._text_result(
                event,
                render_error(
                    "作品不可用",
                    f"{GAME_LABELS.get(game, game)} 已在插件配置中禁用。",
                ),
            )
            return
        self._remember_game(event, game)

        max_rows = self.config.get("max_rows_per_message", 30)

        try:
            if sub == "games":
                yield await self._emit(event, render_games(self._monster_idx.list_games()))
                return
            if sub == "monsters":
                monsters = self._monster_idx.list_monsters(game)
                yield await self._emit(event, render_monster_list(game, monsters, max_rows))
                return
            if sub == "skills":
                skills = self._skill_idx.list_skills(game)
                yield await self._emit(event, render_skill_list(game, skills, max_rows))
                return
            if sub in {"monster", "meat", "weak", "rewards", "skill"}:
                if not name_args:
                    yield self._text_result(
                        event,
                        render_error("缺少参数", f"用法: /mh {USAGE[sub]}"),
                    )
                    return
            if sub == "monster":
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(name_args), game)
                yield await self._emit(event, render_monster_info(monster, resolved_game))
                return
            if sub == "meat":
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(name_args), game)
                yield await self._emit(event, render_meat(monster, resolved_game, max_rows))
                return
            if sub == "weak":
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(name_args), game)
                yield await self._emit(event, render_weak(monster, resolved_game))
                return
            if sub == "rewards":
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(name_args), game)
                yield await self._emit(event, render_rewards(monster, resolved_game, max_rows))
                return
            if sub == "skill":
                _, skill, resolved_game = self._skill_idx.lookup(" ".join(name_args), game)
                yield await self._emit(event, render_skill(skill, resolved_game))
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
        """怪物猎人信息查询：肉质 / 弱点 / 素材 / 技能 / 怪物 / 作品"""

    @mh.command("帮助", alias={"help", "用法"})
    async def mh_help(self, event: AstrMessageEvent):
        """查看完整帮助：全部子命令、作品标识与用法示例"""
        async for r in self._dispatch(event, "help"):
            yield r

    @mh.command("怪物列表", alias={"monsters", "怪物表", "list"})
    async def mh_monsters(self, event: AstrMessageEvent):
        """列出该作品的全部大型怪物（用法：/mh 怪物列表 [作品]）"""
        async for r in self._dispatch(event, "monsters"):
            yield r

    @mh.command("怪物", alias={"monster", "info"})
    async def mh_monster(self, event: AstrMessageEvent):
        """查看怪物基础信息：种类 / HR 点数 / 基础 HP（用法：/mh 怪物 <名字> [作品]）"""
        async for r in self._dispatch(event, "monster"):
            yield r

    @mh.command("肉质", alias={"meat", "肉"})
    async def mh_meat(self, event: AstrMessageEvent):
        """查看怪物各部位肉质表：斩 / 打 / 弹 / 火水雷冰龙（用法：/mh 肉质 <名字> [作品]）"""
        async for r in self._dispatch(event, "meat"):
            yield r

    @mh.command("弱点", alias={"weak", "属性"})
    async def mh_weak(self, event: AstrMessageEvent):
        """查看属性弱点概览与状态异常累积值（用法：/mh 弱点 <名字> [作品]）"""
        async for r in self._dispatch(event, "weak"):
            yield r

    @mh.command("素材", alias={"rewards", "报酬", "掉落"})
    async def mh_rewards(self, event: AstrMessageEvent):
        """查看剥取 / 部位破坏 / 目标报酬素材（用法：/mh 素材 <名字> [作品]）"""
        async for r in self._dispatch(event, "rewards"):
            yield r

    @mh.command("技能列表", alias={"skills", "技能表"})
    async def mh_skills(self, event: AstrMessageEvent):
        """列出该作品的全部技能（用法：/mh 技能列表 [作品]）"""
        async for r in self._dispatch(event, "skills"):
            yield r

    @mh.command("技能", alias={"skill"})
    async def mh_skill(self, event: AstrMessageEvent):
        """查看技能各等级效果（用法：/mh 技能 <名字> [作品]）"""
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
        """管理员：从 kiranico 在线刷新该作品数据（用法：/mh 更新 [作品]）"""
        async for r in self._dispatch(event, "update"):
            yield r
