"""Skill index with multi-language name lookup and game scoping."""
from __future__ import annotations

from difflib import get_close_matches
from typing import Any

from .data_loader import get_loader
from .errors import GameDisabled, InvalidGame, SkillNotFound


class SkillIndex:
    def __init__(self) -> None:
        self._by_game: dict[str, dict[str, dict[str, Any]]] = {}
        self._aliases_by_game: dict[str, dict[str, str]] = {}
        self._enabled: dict[str, bool] = {
            "mhworld": True,
            "mhrise": True,
            "mhwilds": True,
        }

    def configure(self, enabled: dict[str, bool]) -> None:
        self._enabled = {**self._enabled, **enabled}

    def is_enabled(self, game: str) -> bool:
        return self._enabled.get(game, True)

    def reload(self, game: str | None = None) -> None:
        loader = get_loader()
        games = [game] if game else ["mhworld", "mhrise", "mhwilds"]
        for g in games:
            try:
                skills = loader.get_skills(g)
            except Exception:
                self._by_game[g] = {}
                self._aliases_by_game[g] = {}
                continue
            by_id: dict[str, dict[str, Any]] = {}
            aliases: dict[str, str] = {}
            for s in skills:
                sid = s.get("id") or s.get("name_en") or s.get("name_zh")
                if not sid:
                    continue
                by_id[sid] = s
                for key in (s.get("name_zh"), s.get("name_en")):
                    if key:
                        aliases.setdefault(key.lower(), sid)
                for alias in s.get("aliases") or []:
                    if alias:
                        aliases.setdefault(alias.lower(), sid)
            self._by_game[g] = by_id
            self._aliases_by_game[g] = aliases

    def list_games(self) -> list[str]:
        return [g for g in ["mhworld", "mhrise", "mhwilds"] if self.is_enabled(g)]

    def list_skills(self, game: str) -> list[dict[str, Any]]:
        self._ensure_game(game)
        return list(self._by_game.get(game, {}).values())

    def lookup(self, query: str, game: str | None = None) -> tuple[str, dict[str, Any], str]:
        if not query:
            raise SkillNotFound(query="", suggestions=[])
        search_order = [game] if game else [g for g in self.list_games() if g]
        for g in search_order:
            try:
                self._ensure_game(g)
            except (InvalidGame, GameDisabled):
                continue
            hit = self._search_in_game(query, g)
            if hit:
                return hit
        for g in self.list_games():
            hit = self._search_in_game(query, g)
            if hit:
                return hit
        suggestions = self._suggestions(query)
        raise SkillNotFound(query=query, suggestions=suggestions)

    # --- internals --------------------------------------------------------

    def _ensure_game(self, game: str) -> None:
        if game not in {"mhworld", "mhrise", "mhwilds"}:
            raise InvalidGame(game=game)
        if not self.is_enabled(game):
            raise GameDisabled(game=game)
        if game not in self._by_game:
            self.reload(game)
        if not self.is_enabled(game):
            raise GameDisabled(game=game)

    def _search_in_game(self, query: str, game: str) -> tuple[str, dict[str, Any], str] | None:
        aliases = self._aliases_by_game.get(game, {})
        ql = query.strip().lower()
        if not ql:
            return None
        if ql in aliases:
            sid = aliases[ql]
            return sid, self._by_game[game][sid], game
        for sid, s in self._by_game[game].items():
            names = [s.get("name_zh") or "", s.get("name_en") or ""] + list(s.get("aliases") or [])
            for n in names:
                if n and ql in n.lower():
                    return sid, s, game
        return None

    def _suggestions(self, query: str) -> list[str]:
        seen: set[str] = set()
        for g in self.list_games():
            for s in self._by_game.get(g, {}).values():
                for n in [s.get("name_zh"), s.get("name_en")] + list(s.get("aliases") or []):
                    if n and n not in seen:
                        seen.add(n)
        return get_close_matches(query, list(seen), n=5, cutoff=0.4)


_module_index: SkillIndex | None = None


def get_skill_index() -> SkillIndex:
    global _module_index
    if _module_index is None:
        _module_index = SkillIndex()
    return _module_index