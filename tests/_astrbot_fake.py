"""A behaviour-faithful stand-in for the slice of the AstrBot API `main.py` uses.

The plugin's command registration has to be testable without AstrBot installed,
so this module mirrors the real implementation of:

* ``astrbot/core/star/register/star_handler.py`` — ``register_command``,
  ``register_command_group`` and the ``RegisteringCommandable`` cascade used by
  ``@mh.command(...)``
* ``astrbot/core/star/filter/command.py`` — ``CommandFilter`` matching
  (normalise whitespace, then require a token boundary) and parameter typing
* ``astrbot/core/star/filter/command_group.py`` — ``CommandGroupFilter``
  (``startswith`` / ``equals`` / ``print_cmd_tree``)
* ``astrbot/core/pipeline/waking_check/stage.py`` — the wake prefix is stripped
  from ``event.message_str`` before filters run, and a handler carrying a
  ``CommandGroupFilter`` is never executed directly

Public API
----------
``install()``          install fake ``astrbot`` modules into ``sys.modules``
``load_plugin()``      import ``main.py`` the way AstrBot does (idempotent)
``make_plugin()``      instantiate the plugin class with redirectable state
``registry()``         every registered handler, in registration order
``dispatch()``         route a message and run the matched handler
"""
from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple

REPO = Path(__file__).resolve().parent.parent
MODULE_NAME = "astrbot_plugin_mhhelper.main"

ADMIN = "admin"

# --------------------------------------------------------------------------
# AstrBot filter doubles
# --------------------------------------------------------------------------


@dataclass
class Handler:
    """Stand-in for ``StarHandlerMetadata``."""

    name: str
    full_name: str
    func: Callable
    desc: str
    filt: object
    is_group: bool
    is_sub: bool
    permission: str | None = None

    @property
    def is_admin_only(self) -> bool:
        return self.permission == ADMIN


@dataclass
class CommandFilter:
    """Mirrors ``astrbot.core.star.filter.command.CommandFilter``."""

    command_name: str
    alias: set = field(default_factory=set)
    parent_command_names: list[str] = field(default_factory=lambda: [""])
    desc: str = ""

    def complete_names(self) -> list[str]:
        names = [self.command_name, *sorted(self.alias)]
        return [
            f"{p} {c}" if p else c
            for c in names
            for p in self.parent_command_names
        ]

    def match(self, message_str: str) -> bool:
        msg = re.sub(r"\s+", " ", message_str.strip())
        return any(
            msg == full or msg.startswith(full + " ") for full in self.complete_names()
        )

    def print_types(self) -> str:
        # Our sub-commands parse their own arguments, so AstrBot sees no params
        # and renders ``(无参数指令)`` in the tree.
        return ""


class CommandGroupFilter:
    """Mirrors ``astrbot.core.star.filter.command_group.CommandGroupFilter``."""

    def __init__(self, group_name: str, alias: set | None = None, parent_group=None):
        self.group_name = group_name
        self.alias = alias or set()
        self.sub_commands: list = []
        self.parent_group = parent_group

    def complete_names(self) -> list[str]:
        if self.parent_group is None:
            return [self.group_name, *sorted(self.alias)]
        return [
            f"{p} {c}"
            for p in self.parent_group.complete_names()
            for c in [self.group_name, *sorted(self.alias)]
        ]

    def startswith(self, message_str: str) -> bool:
        return message_str.startswith(tuple(self.complete_names()))

    def equals(self, message_str: str) -> bool:
        return message_str in self.complete_names()

    def print_cmd_tree(self, prefix: str = "") -> str:
        parts = []
        for sub in self.sub_commands:
            if isinstance(sub, CommandFilter):
                line = f"{prefix}├── {sub.command_name}"
                types = sub.print_types()
                line += f" ({types})" if types else " (无参数指令)"
                if sub.desc:
                    line += f": {sub.desc}"
                parts.append(line + "\n")
            else:
                parts.append(f"{prefix}├── {sub.group_name}\n")
                parts.append(sub.print_cmd_tree(prefix + "│   "))
        return "".join(parts)


# --------------------------------------------------------------------------
# Registration doubles
# --------------------------------------------------------------------------

_REGISTRY: list[Handler] = []
_BY_FULL_NAME: dict[str, Handler] = {}


def registry() -> list[Handler]:
    return list(_REGISTRY)


def _full_name(fn: Callable) -> str:
    return f"{fn.__module__}_{fn.__name__}"


class _RegisteringCommandable:
    """Mirrors ``astrbot.core.star.register.RegisteringCommandable``."""

    def __init__(self, group: CommandGroupFilter) -> None:
        self.group = group

    def command(self, sub_command: str, alias: set | None = None):
        return _register_command(self, sub_command, alias=alias)

    def group(self, sub_command: str, alias: set | None = None):
        return _register_command_group(self, sub_command, alias=alias)


def _register_command(command_name, sub_command=None, alias=None, **_kw):
    if isinstance(command_name, _RegisteringCommandable):
        cf = CommandFilter(sub_command, alias, command_name.group.complete_names())
        command_name.group.sub_commands.append(cf)
        is_sub = True
    else:
        cf = CommandFilter(command_name, alias)
        is_sub = False

    def decorator(fn):
        handler = Handler(
            name=fn.__name__,
            full_name=_full_name(fn),
            func=fn,
            desc=(fn.__doc__ or "").strip(),
            filt=cf,
            is_group=False,
            is_sub=is_sub,
        )
        cf.desc = handler.desc
        _REGISTRY.append(handler)
        _BY_FULL_NAME[handler.full_name] = handler
        return fn

    return decorator


def _register_command_group(command_name, sub_command=None, alias=None, **_kw):
    if isinstance(command_name, _RegisteringCommandable):
        gf = CommandGroupFilter(sub_command, alias, parent_group=command_name.group)
        command_name.group.sub_commands.append(gf)
    else:
        gf = CommandGroupFilter(command_name, alias)

    def decorator(obj):
        handler = Handler(
            name=obj.__name__,
            full_name=_full_name(obj),
            func=obj,
            desc=(obj.__doc__ or "").strip(),
            filt=gf,
            is_group=True,
            is_sub=False,
        )
        _REGISTRY.append(handler)
        _BY_FULL_NAME[handler.full_name] = handler
        return _RegisteringCommandable(gf)

    return decorator


def _register_permission_type(permission, *_a, **_kw):
    def decorator(fn):
        _BY_FULL_NAME[_full_name(fn)].permission = permission
        return fn

    return decorator


class _PermissionType:
    ADMIN = ADMIN
    MEMBER = "member"


class _Filter:
    command = staticmethod(_register_command)
    command_group = staticmethod(_register_command_group)
    permission_type = staticmethod(_register_permission_type)
    PermissionType = _PermissionType


# --------------------------------------------------------------------------
# Event / plugin doubles
# --------------------------------------------------------------------------


class _FakeEvent:
    def __init__(self, message_str: str, sender_id: str = "10001",
                 platform: str = "aiocqhttp", role: str = "member"):
        self.message_str = message_str
        self._sender_id = sender_id
        self.platform = platform
        self.role = role
        self.unified_msg_origin = f"{platform}:GroupMessage:{sender_id}"

    def is_admin(self) -> bool:
        return self.role == "admin"

    def get_sender_id(self) -> str:
        return self._sender_id

    def get_platform_name(self) -> str:
        return self.platform

    def plain_result(self, text: str) -> str:
        return text

    def image_result(self, url: str) -> str:
        return f"[image] {url}"


class _Star:
    def __init__(self, context=None, *a, **kw):
        self.context = context


def _register_plugin(name, author, desc, version):
    def deco(cls):
        return cls

    return deco


def install() -> None:
    """Install fake ``astrbot`` modules so ``main.py`` can be imported."""
    if "astrbot.api.event" in sys.modules:
        return

    fake_astrbot = types.ModuleType("astrbot")
    fake_api = types.ModuleType("astrbot.api")
    fake_event = types.ModuleType("astrbot.api.event")
    fake_star = types.ModuleType("astrbot.api.star")
    fake_core = types.ModuleType("astrbot.core")
    fake_core_config = types.ModuleType("astrbot.core.config")
    fake_config = types.ModuleType("astrbot.core.config.astrbot_config")

    fake_event.filter = _Filter
    fake_event.AstrMessageEvent = _FakeEvent
    fake_star.Star = _Star
    fake_star.register = _register_plugin
    fake_config.AstrBotConfig = dict

    sys.modules.update(
        {
            "astrbot": fake_astrbot,
            "astrbot.api": fake_api,
            "astrbot.api.event": fake_event,
            "astrbot.api.star": fake_star,
            "astrbot.core": fake_core,
            "astrbot.core.config": fake_core_config,
            "astrbot.core.config.astrbot_config": fake_config,
        }
    )


_MODULE = None


def load_plugin():
    """Import ``main.py`` as ``astrbot_plugin_mhhelper.main`` (idempotent)."""
    global _MODULE
    if _MODULE is not None:
        return _MODULE
    install()
    spec = importlib.util.spec_from_file_location(MODULE_NAME, REPO / "main.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = mod
    spec.loader.exec_module(mod)
    _MODULE = mod
    return mod


class _FakeConfig(dict):
    """Plugin config that remembers whether it has been persisted."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.saved = False

    def save_config(self) -> None:
        self.saved = True


def make_plugin(state_dir: Path | None = None, config: dict | None = None):
    """Instantiate the plugin.

    ``state_dir`` is accepted (and ignored) for backwards compatibility with
    tests written before the plugin stopped keeping its own state file — the
    current game now lives in the plugin *config* and is persisted by AstrBot.
    """
    mod = load_plugin()
    inst = mod.MHHelperPlugin(None, None)   # 用插件自己的默认值填充
    cfg = _FakeConfig(inst.config)          # dict 子类，带 save_config
    if config:
        cfg.update(config)
    inst.config = cfg
    inst._init_indexes()                    # 配置变了，启用集合要重算
    return inst


def root_groups() -> list[CommandGroupFilter]:
    return [h.filt for h in _REGISTRY if h.is_group]


def top_level_commands() -> list[Handler]:
    """Handlers registered as bare commands — these are what clutter the panel."""
    return [h for h in _REGISTRY if not h.is_group and not h.is_sub]


# --------------------------------------------------------------------------
# WakingCheckStage + dispatch simulation
# --------------------------------------------------------------------------

WAKE_PREFIXES = ("/", "!", "！")


def _strip_wake(message: str) -> str:
    for prefix in WAKE_PREFIXES:
        if message.startswith(prefix):
            return message[len(prefix):].strip()
    return message.strip()


class Dispatch(NamedTuple):
    tree: str | None
    handlers: list[str]
    text: str
    message: str
    blocked: bool


async def _collect(handler: Handler, plugin, event: _FakeEvent) -> list[str]:
    return [result async for result in handler.func(plugin, event)]


def dispatch(
    plugin,
    message: str,
    sender_id: str = "10001",
    as_admin: bool = False,
    platform: str = "aiocqhttp",
) -> Dispatch:
    """Route `message` the way AstrBot would, then run the matched handler.

    ``tree`` is set when the message addresses the bare command group, in which
    case AstrBot raises "参数不足" and renders the group tree instead of
    executing anything. ``blocked`` is True when the matched handler needs
    ADMIN permission and the caller is not an admin.

    ``platform`` feeds ``event.get_platform_name()``, which drives the plugin's
    ``output_mode="auto"`` choice (aiocqhttp → image, telegram → markdown, …).
    The fake plugin has no ``html_render``, so image mode degrades to plain text.
    """
    msg = _strip_wake(message)
    hits: list[Handler] = []
    for handler in _REGISTRY:
        if handler.is_group:
            if handler.filt.equals(msg):
                filt = handler.filt
                return Dispatch(
                    tree=f"{filt.group_name}\n{filt.print_cmd_tree()}",
                    handlers=[],
                    text="",
                    message=msg,
                    blocked=False,
                )
            continue  # a command-group handler is never executed directly
        if handler.filt.match(msg):
            hits.append(handler)

    blocked = bool(hits) and hits[0].is_admin_only and not as_admin
    text = ""
    if hits and not blocked:
        event = _FakeEvent(message, sender_id, platform,
                           role="admin" if as_admin else "member")
        text = "\n".join(asyncio.run(_collect(hits[0], plugin, event)))
    return Dispatch(
        tree=None,
        handlers=[h.name for h in hits],
        text=text,
        message=msg,
        blocked=blocked,
    )


__all__ = [
    "ADMIN",
    "CommandFilter",
    "CommandGroupFilter",
    "Dispatch",
    "Handler",
    "dispatch",
    "install",
    "load_plugin",
    "make_plugin",
    "registry",
    "root_groups",
    "top_level_commands",
]
