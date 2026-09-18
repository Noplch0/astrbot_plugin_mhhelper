"""Test fixture loader: redirect DataLoader to use the sample JSON files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

_DATA: dict[tuple[str, str], Any] = {}


def load_fixture(kind: str, game: str) -> Any:
    """Return the sample JSON payload for (kind, game)."""
    key = (kind, game)
    if key not in _DATA:
        path = FIXTURE_DIR / f"{kind}_sample.json"
        with path.open(encoding="utf-8") as f:
            _DATA[key] = json.load(f)
    return _DATA[key]


def install_fake_loader(monkeypatch) -> None:
    """Patch every DataLoader instance to read from fixtures."""
    from core import data_loader
    from core.errors import DataNotLoaded

    def _fake_load(self, kind, game):  # noqa: ANN001
        try:
            return load_fixture(kind, game)
        except FileNotFoundError as exc:
            raise DataNotLoaded(game=game, file=str(exc)) from exc

    monkeypatch.setattr(data_loader.DataLoader, "_load_from_disk", _fake_load)