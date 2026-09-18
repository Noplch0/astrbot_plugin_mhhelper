"""AstrBot plugin entry: Monster Hunter information lookup (MHWorld / MHRise / MHWilds).

Every subcommand is registered as a first-class AstrBot command so each one
appears in the admin UI's command list (where the previous single-decorator
version only exposed `mh` itself).

Registered commands:

  /mh                show help
  /mh肉质 <名> [game]    meat / hit zone table
  /mh弱点 <名> [game]    elemental weakness + ailments
  /mh素材 <名> [game]    carve / break / reward materials
  /mh怪物 <名> [game]    monster basic info
  /mh怪物列表 [game]     list large monsters in the given game
  /mh技能 <名> [game]    skill level effects
  /mh技能列表 [game]      list skills in the given game
  /mh作品             list enabled games
  /mh更新 [game]      admin: refresh data from kiranico

Each handler also accepts the corresponding English form
(mh_meat, mh_weak, mh_monster, mh_monsters, mh_skill, mh_skills,
mh_games, mh_update, mh_help).

`game` is optional and defaults to the user's last-used game (or mhwilds).
Game identifiers: mhworld / mhrise / mhwilds  (and 世界 / 崛起 / 荒野 etc.).
"""
from __future__ import annotations

import json
import logging
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
from core.skill_index import get_skill_index  # noqa: E402

log = logging.getLogger("astrbot-mhhelper")

PLUGIN_NAME = "astrbot_plugin_mhhelper"

GAME_ALIASES: dict[str, str] = {
    "world": "mhworld",
    "mhworld": "mhworld",
    "rise": "mhrise",
    "mhrise": "mhrise",
    "wilds": "mhwilds",
    "mhwilds": "mhwilds",
    "荒野": "mhwilds",
    "崛起": "mhrise",
    "世界": "mhworld",
    "曙光": "mhrise",
}


def _resolve_game(token: str | None) -> str:
    """Return canonical game key for a user-provided token."""
    if not token:
        return "mhwilds"
    key = token.strip().lower().replace(" ", "")
    return GAME_ALIASES.get(key, key)


def _looks_like_game(token: str) -> bool:
    return token in GAMES or token in GAME_ALIASES


@register(PLUGIN_NAME, "Noplch0", "怪物猎人信息查询 (MHWorld / MHRise / MHWilds)", "0.1.0")
class MHHelperPlugin(Star):
    def __init__(self, context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or self._default_config()
        self._data_root = Path(__file__).resolve().parent
        self._state_path = self._plugin_state_dir() / "user_last_game.json"
        self._user_game_cache: dict[str, str] = self._load_user_state()
        self._init_indexes()

    # ------------------- lifecycle -------------------

    async def initialize(self) -> None:
        self._init_indexes()
        log.info("[%s] loaded.", PLUGIN_NAME)

    async def terminate(self) -> None:
        self._save_user_state()

    # ------------------- internal helpers -------------------

    def _plugin_state_dir(self) -> Path:
        candidate = self._data_root / "plugin_data"
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    def _default_config(self) -> dict[str, Any]:
        return {
            "default_game": "mhwilds",
            "enable_world": True,
            "enable_rise": True,
            "enable_wilds": True,
            "with_icon": False,
            "proxy": "",
            "max_rows_per_message": 30,
            "allow_runtime_update": True,
        }

    def _init_indexes(self) -> None:
        loader = get_loader()
        loader.invalidate()
        self._monster_idx = get_monster_index()
        self._monster_idx.configure(
            {
                "mhworld": bool(self.config.get("enable_world", True)),
                "mhrise": bool(self.config.get("enable_rise", True)),
                "mhwilds": bool(self.config.get("enable_wilds", True)),
            }
        )
        self._skill_idx = get_skill_index()
        self._skill_idx.configure(
            {
                "mhworld": bool(self.config.get("enable_world", True)),
                "mhrise": bool(self.config.get("enable_rise", True)),
                "mhwilds": bool(self.config.get("enable_wilds", True)),
            }
        )
        for g in GAMES:
            try:
                self._monster_idx.reload(g)
                self._skill_idx.reload(g)
            except DataNotLoaded:
                log.warning("[%s] data missing for %s", PLUGIN_NAME, g)

    def _load_user_state(self) -> dict[str, str]:
        if self._state_path.is_file():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_user_state(self) -> None:
        try:
            self._state_path.write_text(
                json.dumps(self._user_game_cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning("Failed to save user state: %s", exc)

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
    def _strip_command(message_str: str, command: str) -> str:
        """Strip a leading `/command` (case-insensitive, optional slash) from message_str."""
        text = (message_str or "").lstrip()
        for v in (f"/{command}", command):
            if text[: len(v)].lower() == v.lower():
                return text[len(v):].lstrip()
        return text

    # ------------------- shared dispatch -------------------

    async def _dispatch(self, event: AstrMessageEvent, sub: str, raw_body: str):
        """Single dispatch used by every command handler.

        `raw_body` is the message text with the leading command token already
        stripped — it's where we look for `[<name>...] [<game>]`.
        """
        parts = raw_body.strip().split()
        game_hint = None
        # Last token may be a game hint
        if parts and _looks_like_game(parts[-1]):
            game_hint = _resolve_game(parts[-1])
            parts = parts[:-1]
        elif sub in {"monsters", "skills", "games", "update"} and parts:
            # These subcommands take an optional single game hint
            only = _resolve_game(parts[0])
            if only in GAMES:
                game_hint = only
                parts = parts[1:]
        name_args = parts

        game = game_hint or self._user_default_game(event)
        if game not in GAMES:
            yield event.plain_result(render_error("未知作品", f"未识别的作品标识: {game}", list(GAME_LABELS)))
            return
        self._remember_game(event, game)

        try:
            if sub == "help":
                yield event.plain_result(render_help())
                return
            if sub == "games":
                yield event.plain_result(render_games(self._monster_idx.list_games()))
                return
            if sub == "monsters":
                monsters = self._monster_idx.list_monsters(game)
                yield event.plain_result(
                    render_monster_list(game, monsters, self.config.get("max_rows_per_message", 30))
                )
                return
            if sub == "skills":
                skills = self._skill_idx.list_skills(game)
                yield event.plain_result(
                    render_skill_list(game, skills, self.config.get("max_rows_per_message", 30))
                )
                return
            if sub == "monster":
                if not name_args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh怪物 <名字> [作品]"))
                    return
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(name_args), game)
                yield event.plain_result(render_monster_info(monster, resolved_game))
                return
            if sub == "meat":
                if not name_args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh肉质 <名字> [作品]"))
                    return
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(name_args), game)
                yield event.plain_result(
                    render_meat(monster, resolved_game, self.config.get("max_rows_per_message", 30))
                )
                return
            if sub == "weak":
                if not name_args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh弱点 <名字> [作品]"))
                    return
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(name_args), game)
                yield event.plain_result(render_weak(monster, resolved_game))
                return
            if sub == "rewards":
                if not name_args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh素材 <名字> [作品]"))
                    return
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(name_args), game)
                yield event.plain_result(
                    render_rewards(monster, resolved_game, self.config.get("max_rows_per_message", 30))
                )
                return
            if sub == "skill":
                if not name_args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh技能 <名字> [作品]"))
                    return
                _, skill, resolved_game = self._skill_idx.lookup(" ".join(name_args), game)
                yield event.plain_result(render_skill(skill, resolved_game))
                return
            if sub == "update":
                async for r in self._cmd_update(game):
                    yield r
                return
            yield event.plain_result(render_help())
        except MonsterNotFound as exc:
            yield event.plain_result(
                render_error("未找到怪物", f"在 {GAME_LABELS.get(game, game)} 中找不到: {exc.query}", exc.suggestions)
            )
        except SkillNotFound as exc:
            yield event.plain_result(
                render_error("未找到技能", f"在 {GAME_LABELS.get(game, game)} 中找不到: {exc.query}", exc.suggestions)
            )
        except DataNotLoaded as exc:
            yield event.plain_result(
                render_error(
                    "数据未加载",
                    f"该作品的数据未就绪。请联系管理员执行 /mh更新 {exc.game} 或重新安装插件。",
                )
            )
        except (InvalidGame, GameDisabled) as exc:
            yield event.plain_result(render_error("作品不可用", str(exc)))
        except Exception as exc:  # noqa: BLE001
            log.exception("Handler error: %s", exc)
            yield event.plain_result(render_error("内部错误", str(exc)))

    async def _cmd_update(self, game: str):
        if not self.config.get("allow_runtime_update", True):
            yield event.plain_result(render_error("已禁用", "管理员已禁用在线刷新。请让管理员重新安装插件。"))
            return
        yield event.plain_result(f"⏳ 正在从 kiranico 拉取 {GAME_LABELS.get(game, game)} 数据…")
        try:
            from scraper.common import SCRAPERS
            from scraper.run_update import refresh_game
        except ImportError as e:
            yield event.plain_result(render_error("抓取模块不可用", str(e)))
            return
        if game not in SCRAPERS:
            yield event.plain_result(render_error("未知作品", game))
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
        yield event.plain_result(render_update_result(game, monsters, skills, time.time() - t0))

    # ------------------- registered commands -------------------
    # Each `@filter.command(...)` makes the subcommand individually visible
    # in AstrBot's admin command list. They all dispatch to `_dispatch(...)`.

    @filter.command("mh")
    async def cmd_mh(self, event: AstrMessageEvent):
        """`/mh` — show help."""
        body = self._strip_command(event.message_str, "mh")
        async for r in self._dispatch(event, "help", body):
            yield r

    @filter.command("mh_help")
    @filter.command("mh帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        """`/mh_help` / `/mh帮助` — show help."""
        body = self._strip_command(event.message_str, "mh_help")
        async for r in self._dispatch(event, "help", body):
            yield r

    # ----- meat / 肉质 -----
    @filter.command("mh肉质")
    @filter.command("mh_meat")
    async def cmd_meat(self, event: AstrMessageEvent):
        body = self._strip_command(event.message_str, "mh肉质")
        async for r in self._dispatch(event, "meat", body):
            yield r

    # ----- weak / 弱点 -----
    @filter.command("mh弱点")
    @filter.command("mh_weak")
    async def cmd_weak(self, event: AstrMessageEvent):
        body = self._strip_command(event.message_str, "mh弱点")
        async for r in self._dispatch(event, "weak", body):
            yield r

    # ----- rewards / 素材 -----
    @filter.command("mh素材")
    @filter.command("mh_rewards")
    async def cmd_rewards(self, event: AstrMessageEvent):
        body = self._strip_command(event.message_str, "mh素材")
        async for r in self._dispatch(event, "rewards", body):
            yield r

    # ----- monster / 怪物 (info) -----
    @filter.command("mh怪物")
    @filter.command("mh_monster")
    async def cmd_monster(self, event: AstrMessageEvent):
        body = self._strip_command(event.message_str, "mh怪物")
        async for r in self._dispatch(event, "monster", body):
            yield r

    # ----- monsters / 怪物列表 -----
    @filter.command("mh怪物列表")
    @filter.command("mh_monsters")
    async def cmd_monsters(self, event: AstrMessageEvent):
        body = self._strip_command(event.message_str, "mh怪物列表")
        async for r in self._dispatch(event, "monsters", body):
            yield r

    # ----- skill / 技能 (info) -----
    @filter.command("mh技能")
    @filter.command("mh_skill")
    async def cmd_skill(self, event: AstrMessageEvent):
        body = self._strip_command(event.message_str, "mh技能")
        async for r in self._dispatch(event, "skill", body):
            yield r

    # ----- skills / 技能列表 -----
    @filter.command("mh技能列表")
    @filter.command("mh_skills")
    async def cmd_skills(self, event: AstrMessageEvent):
        body = self._strip_command(event.message_str, "mh技能列表")
        async for r in self._dispatch(event, "skills", body):
            yield r

    # ----- games / 作品 -----
    @filter.command("mh作品")
    @filter.command("mh_games")
    async def cmd_games(self, event: AstrMessageEvent):
        body = self._strip_command(event.message_str, "mh作品")
        async for r in self._dispatch(event, "games", body):
            yield r

    # ----- update / 更新 -----
    @filter.command("mh更新")
    @filter.command("mh_update")
    async def cmd_update(self, event: AstrMessageEvent):
        body = self._strip_command(event.message_str, "mh更新")
        async for r in self._dispatch(event, "update", body):
            yield r