"""Monster index with multi-language name lookup and game scoping."""
from __future__ import annotations

from difflib import get_close_matches
from typing import Any

from .data_loader import get_loader
from .errors import GameDisabled, InvalidGame, MonsterNotFound


class MonsterIndex:
    """In-memory index built from DataLoader for fast lookup."""

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
        games = [game] if game else list(self._by_game.keys() or ["mhworld", "mhrise", "mhwilds"])
        for g in games:
            try:
                monsters = loader.get_monsters(g)
            except Exception:
                self._by_game[g] = {}
                self._aliases_by_game[g] = {}
                continue
            by_id: dict[str, dict[str, Any]] = {}
            aliases: dict[str, str] = {}
            for m in monsters:
                mid = m.get("id") or m.get("name_en") or m.get("name_zh")
                if not mid:
                    continue
                by_id[mid] = m
                for key in (m.get("name_zh"), m.get("name_en")):
                    if key:
                        aliases.setdefault(key.lower(), mid)
                for alias in m.get("aliases") or []:
                    if alias:
                        aliases.setdefault(alias.lower(), mid)
            self._by_game[g] = by_id
            self._aliases_by_game[g] = aliases

    def list_games(self) -> list[str]:
        return [g for g in ["mhworld", "mhrise", "mhwilds"] if self.is_enabled(g)]

    def list_monsters(self, game: str) -> list[dict[str, Any]]:
        self._ensure_game(game)
        return list(self._by_game.get(game, {}).values())

    def lookup(self, query: str, game: str | None = None) -> tuple[str, dict[str, Any], str]:
        """Resolve a monster query to (monster_id, monster, game).

        Search order:
        1. exact match on name_zh / name_en / alias within scoped game
        2. substring match
        3. fuzzy match
        Raises MonsterNotFound with suggestions if nothing matches.
        """
        if not query:
            raise MonsterNotFound(query="", suggestions=[])

        # If a specific game is given, only search that one; otherwise try all.
        search_order = [game] if game else [g for g in self.list_games() if g]
        for g in search_order:
            try:
                self._ensure_game(g)
            except (InvalidGame, GameDisabled):
                continue
            hit = self._search_in_game(query, g)
            if hit:
                return hit
        # Last-ditch: try across games even if game was set (so single-game disabled doesn't swallow results)
        for g in self.list_games():
            hit = self._search_in_game(query, g)
            if hit:
                return hit
        suggestions = self._suggestions(query)
        raise MonsterNotFound(query=query, suggestions=suggestions)

    # --- internals --------------------------------------------------------

    def _ensure_game(self, game: str) -> None:
        if game not in {"mhworld", "mhrise", "mhwilds"}:
            raise InvalidGame(game=game)
        if not self.is_enabled(game):
            raise GameDisabled(game=game)
        if game not in self._by_game:
            self.reload(game)
        # If the game has been disabled since the data was cached, raise now.
        if not self.is_enabled(game):
            raise GameDisabled(game=game)

    def _search_in_game(self, query: str, game: str) -> tuple[str, dict[str, Any], str] | None:
        aliases = self._aliases_by_game.get(game, {})
        ql = query.strip().lower()
        if not ql:
            return None
        # exact
        if ql in aliases:
            mid = aliases[ql]
            return mid, self._by_game[game][mid], game
        # substring over all monster names
        for mid, m in self._by_game[game].items():
            names = [m.get("name_zh") or "", m.get("name_en") or ""] + list(m.get("aliases") or [])
            for n in names:
                if n and ql in n.lower():
                    return mid, m, game
        return None

    def _suggestions(self, query: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for g in self.list_games():
            for m in self._by_game.get(g, {}).values():
                for n in [m.get("name_zh"), m.get("name_en")] + list(m.get("aliases") or []):
                    if n and n not in seen:
                        seen.add(n)
        close = get_close_matches(query, list(seen), n=5, cutoff=0.4)
        return close


_module_index: MonsterIndex | None = None


def get_monster_index() -> MonsterIndex:
    global _module_index
    if _module_index is None:
        _module_index = MonsterIndex()
    return _module_index