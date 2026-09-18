"""Unit tests for core.data_loader."""
from core.data_loader import DataLoader
from core.errors import DataNotLoaded

from ._setup import install_fake_loader


def test_data_loader_uses_fixtures(monkeypatch):
    install_fake_loader(monkeypatch)
    loader = DataLoader()
    monsters = loader.get_monsters("mhworld")
    assert len(monsters) == 2
    skills = loader.get_skills("mhworld")
    assert len(skills) == 2


def test_data_loader_missing_file(monkeypatch):
    install_fake_loader(monkeypatch)

    class MissingLoader(DataLoader):
        def _load_from_disk(self, kind, game):
            raise DataNotLoaded(game=game, file="missing")

    loader = MissingLoader()
    with __import__("pytest").raises(DataNotLoaded):
        loader.get_monsters("missing")


def test_data_loader_invalidate(monkeypatch):
    install_fake_loader(monkeypatch)
    loader = DataLoader()
    loader.get_monsters("mhworld")
    loader.invalidate(kind="monsters", game="mhworld")
    # After invalidate, calling get_monsters again should hit fixtures again
    monsters = loader.get_monsters("mhworld")
    assert len(monsters) == 2