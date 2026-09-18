"""Lazy JSON data loader with LRU cache and per-game invalidation."""
from __future__ import annotations

import json
import logging
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from .errors import DataNotLoaded

log = logging.getLogger("astrbot-mhhelper.data")

GAMES: tuple[str, ...] = ("mhworld", "mhrise", "mhwilds")
GAME_LABELS: dict[str, str] = {
    "mhworld": "怪物猎人:世界",
    "mhrise": "怪物猎人:崛起",
    "mhwilds": "怪物猎人:荒野",
}


def _resolve_data_dir() -> Path:
    """Resolve the canonical data directory at the repo root."""
    here = Path(__file__).resolve()
    # core/ -> repo root
    return here.parent.parent / "data"


DATA_DIR: Path = _resolve_data_dir()


class DataLoader:
    """Lazy JSON loader keyed by (kind, game)."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or DATA_DIR
        self._cache: dict[tuple[str, str], Any] = {}
        self._lock = threading.Lock()
        self._available: dict[tuple[str, str], bool] = {}

    # --- public API -------------------------------------------------------

    def is_available(self, kind: str, game: str) -> bool:
        key = (kind, game)
        with self._lock:
            if key not in self._available:
                self._available[key] = self._file_path(kind, game).is_file()
            return self._available[key]

    def get(self, kind: str, game: str) -> Any:
        """Return cached payload for (kind, game).

        kind ∈ {"monsters", "skills", "meta"}.
        Raises DataNotLoaded if file is missing or JSON is invalid.
        """
        key = (kind, game)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        payload = self._load_from_disk(kind, game)
        with self._lock:
            self._cache[key] = payload
        return payload

    def get_monsters(self, game: str) -> list[dict[str, Any]]:
        return list(self.get("monsters", game).get("monsters", []))

    def get_skills(self, game: str) -> list[dict[str, Any]]:
        return list(self.get("skills", game).get("skills", []))

    def get_meta(self) -> dict[str, Any]:
        meta_path = self._data_dir / "meta.json"
        if not meta_path.is_file():
            return {}
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("meta.json unreadable: %s", exc)
            return {}

    def invalidate(self, kind: str | None = None, game: str | None = None) -> None:
        """Drop cached entries. None matches all."""
        with self._lock:
            keys = list(self._cache.keys())
            for key in keys:
                k_kind, k_game = key
                if (kind is None or k_kind == kind) and (game is None or k_game == game):
                    self._cache.pop(key, None)
            avail_keys = list(self._available.keys())
            for key in avail_keys:
                k_kind, k_game = key
                if (kind is None or k_kind == kind) and (game is None or k_game == game):
                    self._available.pop(key, None)

    def clear(self) -> None:
        self.invalidate()

    # --- internals --------------------------------------------------------

    def _file_path(self, kind: str, game: str) -> Path:
        if kind == "meta":
            return self._data_dir / "meta.json"
        return self._data_dir / kind / f"{game}.json"

    def _load_from_disk(self, kind: str, game: str) -> Any:
        path = self._file_path(kind, game)
        if not path.is_file():
            raise DataNotLoaded(game=game, file=str(path.relative_to(self._data_dir)))
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            log.error("Failed to parse %s: %s", path, exc)
            raise DataNotLoaded(game=game, file=str(path.relative_to(self._data_dir))) from exc


# Module-level singleton
_loader_singleton: DataLoader | None = None


def get_loader() -> DataLoader:
    global _loader_singleton
    if _loader_singleton is None:
        _loader_singleton = DataLoader()
    return _loader_singleton


# Re-export lru_cache for back-compat (some legacy code used it)
__all__ = [
    "GAMES",
    "GAME_LABELS",
    "DataLoader",
    "get_loader",
    "lru_cache",
]