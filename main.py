"""AstrBot plugin entry: Monster Hunter information lookup (MHWorld / MHRise / MHWilds).

Commands (default prefix `/mh`):
- monsters / 怪物列表 [game]
- monster /  <name> [game]
- meat / 肉质 <name> [game]
- weak / 弱点 <name> [game]
- rewards / 素材 <name> [game]
- skills / 技能列表 [game]
- skill / 技能 <name> [game]
- games / 作品
- update / 更新 [game]
- help / 帮助

`game` is optional and defaults to the user's last-used game (or mhwilds).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
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
from core.errors import (
    DataNotLoaded,
    GameDisabled,
    InvalidGame,
    MonsterNotFound,
    SkillNotFound,
)
from core.formatter import (
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
from core.monster_index import get_monster_index
from core.skill_index import get_skill_index

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

SUBCOMMANDS: dict[str, set[str]] = {
    "monsters": {"monsters", "怪物列表", "monsterlist"},
    "monster": {"monster", "怪物"},
    "meat": {"meat", "肉质", "hit"},
    "weak": {"weak", "弱点", "weakness"},
    "rewards": {"rewards", "素材", "drops"},
    "skills": {"skills", "技能列表", "skilllist"},
    "skill": {"skill", "技能"},
    "games": {"games", "作品"},
    "update": {"update", "更新", "refresh"},
    "help": {"help", "帮助", "h"},
}


def _resolve_game(token: str | None) -> str:
    """Return canonical game key for a user-provided token."""
    if not token:
        return "mhwilds"
    key = token.strip().lower().replace(" ", "")
    return GAME_ALIASES.get(key, key)


def _parse_args(text: str) -> tuple[str, list[str]]:
    """Split command body into (subcommand, rest_args)."""
    parts = text.strip().split()
    if not parts:
        return "help", []
    head = parts[0].lower()
    for canonical, aliases in SUBCOMMANDS.items():
        if head in aliases:
            return canonical, parts[1:]
    return "help", parts


@register(PLUGIN_NAME, "mavis", "怪物猎人信息查询 (MHWorld / MHRise / MHWilds)", "0.1.0")
class MHHelperPlugin(Star):
    def __init__(self, context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or _default_config()
        self._data_root = Path(__file__).resolve().parent
        self._state_path = self._plugin_state_dir() / "user_last_game.json"
        self._user_game_cache: dict[str, str] = self._load_user_state()
        self._init_indexes()

    # ------------------- lifecycle -------------------

    async def initialize(self) -> None:
        """Lazy build the indexes now that the plugin is loaded."""
        self._init_indexes()
        log.info(
            "[%s] loaded: mhwilds monsters=%d, mhrise monsters=%d, mhworld monsters=%d",
            PLUGIN_NAME,
            self._monster_idx.list_monsters("mhwilds") and len(self._monster_idx.list_monsters("mhwilds")) or 0,
            len(self._monster_idx.list_monsters("mhrise")),
            len(self._monster_idx.list_monsters("mhworld")),
        )

    async def terminate(self) -> None:
        self._save_user_state()

    # ------------------- internal helpers -------------------

    def _plugin_state_dir(self) -> Path:
        # AstrBot writes per-plugin persistent data under data/<plugin>/.
        # Use the same dir as data/ for simplicity but in plugin_data subdir.
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
                log.warning("[%s] data missing for %s; commands will fail until updated", PLUGIN_NAME, g)

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

    # ------------------- command handler -------------------

    @filter.command("mh")
    async def on_mh(self, event: AstrMessageEvent):
        """Main entry — `/mh <subcommand> [args...]`."""
        raw = event.message_str or ""
        # Strip the leading command prefix
        body = raw
        for prefix in ("/mh", "/MH", "mh ", "MH "):
            if body.startswith(prefix):
                body = body[len(prefix) :]
                break
        body = body.strip()
        sub, args = _parse_args(body)
        # Last token may be a game hint
        game_hint = None
        if args and args[-1].lower() in GAME_ALIASES or (args and args[-1] in GAMES):
            game_hint = _resolve_game(args[-1])
            args = args[:-1]
        # Some subcommands take only a game hint and no name
        if sub in {"monsters", "skills", "games", "update", "help"} and not game_hint and args:
            # Maybe the only arg is a game hint
            only = _resolve_game(args[0])
            if only in GAMES:
                game_hint = only
                args = []
        game = game_hint or self._user_default_game(event)
        if game not in GAMES:
            yield event.plain_result(render_error("未知作品", f"未识别的作品标识: {game}", list(GAME_LABELS)))
            return
        self._remember_game(event, game)

        try:
            if sub == "help":
                yield event.plain_result(render_help())
            elif sub == "games":
                yield event.plain_result(render_games(self._monster_idx.list_games()))
            elif sub == "monsters":
                monsters = self._monster_idx.list_monsters(game)
                yield event.plain_result(
                    render_monster_list(game, monsters, self.config.get("max_rows_per_message", 30))
                )
            elif sub == "skills":
                skills = self._skill_idx.list_skills(game)
                yield event.plain_result(
                    render_skill_list(game, skills, self.config.get("max_rows_per_message", 30))
                )
            elif sub == "monster":
                if not args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh 怪物 <名字> [作品]"))
                    return
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(args), game)
                yield event.plain_result(render_monster_info(monster, resolved_game))
            elif sub == "meat":
                if not args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh 肉质 <名字> [作品]"))
                    return
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(args), game)
                yield event.plain_result(
                    render_meat(monster, resolved_game, self.config.get("max_rows_per_message", 30))
                )
            elif sub == "weak":
                if not args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh 弱点 <名字> [作品]"))
                    return
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(args), game)
                yield event.plain_result(render_weak(monster, resolved_game))
            elif sub == "rewards":
                if not args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh 素材 <名字> [作品]"))
                    return
                _, monster, resolved_game = self._monster_idx.lookup(" ".join(args), game)
                yield event.plain_result(
                    render_rewards(monster, resolved_game, self.config.get("max_rows_per_message", 30))
                )
            elif sub == "skill":
                if not args:
                    yield event.plain_result(render_error("缺少参数", "用法: /mh 技能 <名字> [作品]"))
                    return
                _, skill, resolved_game = self._skill_idx.lookup(" ".join(args), game)
                yield event.plain_result(render_skill(skill, resolved_game))
            elif sub == "update":
                async for r in self._cmd_update(event, game):
                    yield r
            else:
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
                    f"该作品的数据未就绪。请联系管理员执行 /mh 更新 {exc.game} 或重新安装插件。",
                )
            )
        except (InvalidGame, GameDisabled) as exc:
            yield event.plain_result(render_error("作品不可用", str(exc)))
        except Exception as exc:  # noqa: BLE001
            log.exception("Handler error: %s", exc)
            yield event.plain_result(render_error("内部错误", str(exc)))

    async def _cmd_update(self, event: AstrMessageEvent, game: str):
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
        import time
        t0 = time.time()
        monsters, skills = await refresh_game(
            game,
            proxy=self.config.get("proxy") or None,
            concurrency=4,
            delay=0.1,
            only=None,
        )
        # Refresh in-memory indexes
        self._init_indexes()
        yield event.plain_result(render_update_result(game, monsters, skills, time.time() - t0))