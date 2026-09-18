"""Custom exceptions for the MH helper plugin."""


class MHError(Exception):
    """Base exception for the plugin."""


class DataNotLoaded(MHError):
    """Static data files are missing or unreadable."""

    def __init__(self, game: str, file: str) -> None:
        self.game = game
        self.file = file
        super().__init__(f"数据未加载: {game}/{file}")


class MonsterNotFound(MHError):
    """No monster matched the query."""

    def __init__(self, query: str, game: str | None = None, suggestions: list[str] | None = None) -> None:
        self.query = query
        self.game = game
        self.suggestions = suggestions or []
        super().__init__(f"未找到怪物: {query}")


class SkillNotFound(MHError):
    """No skill matched the query."""

    def __init__(self, query: str, game: str | None = None, suggestions: list[str] | None = None) -> None:
        self.query = query
        self.game = game
        self.suggestions = suggestions or []
        super().__init__(f"未找到技能: {query}")


class GameDisabled(MHError):
    """The game has been disabled via config."""

    def __init__(self, game: str) -> None:
        self.game = game
        super().__init__(f"该作品已禁用: {game}")


class InvalidGame(MHError):
    """The game identifier is not recognized."""

    def __init__(self, game: str) -> None:
        self.game = game
        super().__init__(f"未知作品: {game}")