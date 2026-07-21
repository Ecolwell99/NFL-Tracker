from __future__ import annotations
from abc import ABC, abstractmethod
from models.game import Game
from models.drive import Drive, SpecialTeamsScore
from models.play import Play


class FootballDataProvider(ABC):
    """
    Abstract interface for all football data sources.
    The rules engine and UI never import a concrete provider directly.
    Swap ESPN for another source by implementing this interface.
    """

    @abstractmethod
    def get_games(self) -> list[Game]:
        """Return all currently live/active games."""
        ...

    @abstractmethod
    def get_game(self, game_id: str) -> Game:
        """Return game metadata, score, and clock for a single game."""
        ...

    @abstractmethod
    def get_drives(self, game_id: str) -> list[Drive]:
        """Return all drives for a game in chronological order, with plays populated."""
        ...

    @abstractmethod
    def get_plays(self, game_id: str) -> list[Play]:
        """Return all plays for a game in chronological order."""
        ...

    def get_special_teams_scores(self, game_id: str) -> list[SpecialTeamsScore]:
        """Return scores logged with no offensive snaps (e.g. kickoff/punt
        return TDs) that were dropped from the drive list. Optional override."""
        return []

    @abstractmethod
    def get_boxscore(self, game_id: str) -> dict:
        """Return raw boxscore stats dict (team-level aggregates)."""
        ...
