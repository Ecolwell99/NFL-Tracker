from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class GameStatus(Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    HALFTIME = "halftime"
    FINAL = "final"
    POSTPONED = "postponed"
    UNKNOWN = "unknown"


class League(Enum):
    NFL = "NFL"
    CFB = "CFB"


@dataclass
class Team:
    id: str
    name: str           # e.g. "Buccaneers"
    full_name: str      # e.g. "Tampa Bay Buccaneers"
    abbreviation: str   # e.g. "TB"
    color: str          # hex e.g. "#bd1c36"
    alternate_color: str = "#ffffff"
    logo_url: str = ""

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, Team):
            return self.id == other.id
        return NotImplemented


@dataclass
class Score:
    home: int = 0
    away: int = 0


@dataclass
class GameClock:
    period: int = 1
    clock: str = "15:00"       # display string e.g. "7:43"
    is_intermission: bool = False
    is_final: bool = False


@dataclass
class Game:
    game_id: str
    league: League
    home_team: Team
    away_team: Team
    date: str                   # ISO date string
    status: GameStatus = GameStatus.SCHEDULED
    score: Score = field(default_factory=Score)
    clock: GameClock = field(default_factory=GameClock)
    venue: str = ""
    season_type: str = ""       # "preseason", "regular", "postseason"
    week: int | None = None

    @property
    def label(self) -> str:
        return f"{self.away_team.abbreviation} @ {self.home_team.abbreviation} ({self.game_id})"

    @property
    def is_live(self) -> bool:
        return self.status in (GameStatus.IN_PROGRESS, GameStatus.HALFTIME)
