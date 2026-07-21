from __future__ import annotations
from abc import ABC, abstractmethod
from models.game import Game, League
from models.drive import Drive, SpecialTeamsScore
from models.play import Play


class FootballDataProvider(ABC):
    """
    Abstract interface for all football data sources.
    The rules engine and UI never import a concrete provider directly.
    Swap ESPN for another source by implementing this interface.
    """

    @abstractmethod
    def get_games(self, league: League = League.NFL) -> list[Game]:
        """Return all currently live/active games for the given league."""
        ...

    @abstractmethod
    def get_game(self, game_id: str, league: League = League.NFL) -> Game:
        """Return game metadata, score, and clock for a single game."""
        ...

    @abstractmethod
    def get_drives(self, game_id: str, league: League = League.NFL) -> list[Drive]:
        """Return all drives for a game in chronological order, with plays populated."""
        ...

    @abstractmethod
    def get_plays(self, game_id: str, league: League = League.NFL) -> list[Play]:
        """Return all plays for a game in chronological order."""
        ...

    def get_special_teams_scores(self, game_id: str, league: League = League.NFL) -> list[SpecialTeamsScore]:
        """Return scores logged with no offensive snaps (e.g. kickoff/punt
        return TDs) that were dropped from the drive list. Optional override."""
        return []

    @abstractmethod
    def get_boxscore(self, game_id: str, league: League = League.NFL) -> dict:
        """Return raw boxscore stats dict (team-level aggregates)."""
        ...
