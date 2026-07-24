from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from models.game import Team
from models.play import Play, PlayType


class DriveResultGranular(Enum):
    RUSHING_TD = "Rushing TD"
    PASSING_TD = "Passing TD"
    FG_MADE = "FG Made"
    FG_MISSED = "FG Missed"
    PUNT = "Punt"
    TURNOVER_ON_DOWNS_OR_SAFETY = "Turnover on Downs or Safety"
    INTERCEPTION = "Interception"
    FUMBLE = "Fumble"
    END_OF_HALF = "End of Half"
    UNKNOWN = "Unknown"


class DriveResultExact(Enum):
    TD = "TD"
    FG = "FG Attempt"
    PUNT = "Punt"
    TURNOVER = "Turnover"
    VOID = "Void"
    UNKNOWN = "Unknown"


class DriveResultGrouped(Enum):
    OFFENSIVE_SCORE = "Offensive Score"
    NO_OFFENSIVE_SCORE = "No Offensive Score"
    VOID = "Void"
    UNKNOWN = "Unknown"


@dataclass
class DriveResult:
    granular: DriveResultGranular
    exact: DriveResultExact
    grouped: DriveResultGrouped


@dataclass
class SpecialTeamsScore:
    """A scoring 'drive' ESPN logs with zero offensive snaps — e.g. a kickoff
    or punt return TD. Not a real offensive drive, so it is dropped from the
    drive list and surfaced as an inline marker instead."""
    team: Team
    sequence: float             # sort key that interleaves with Drive.sequence
    espn_result: str = ""       # raw ESPN result, e.g. "TD"
    score_home: int = 0
    score_away: int = 0


@dataclass
class Drive:
    drive_id: str
    game_id: str
    sequence: int               # chronological order across whole game
    team: Team
    team_drive_number: int      # this team's Nth drive
    plays: list[Play] = field(default_factory=list)

    # Field position — yards to endzone (0 = opponent endzone, 100 = own endzone)
    start_yardline: int = 0
    end_yardline: int = 0

    # Raw yard line number and ESPN-formatted text for display (e.g. "CAR 35")
    start_yardline_raw: int = 0
    start_text: str = ""

    yards_gained: int = 0
    time_of_possession: str = ""
    play_count: int = 0
    description: str = ""       # ESPN raw e.g. "9 plays, 56 yards, 4:30"

    # Score at the end of this drive
    score_home: int = 0
    score_away: int = 0

    # True if this is the currently active drive (live game)
    is_current: bool = False

    # ESPN raw result string — used as fallback
    espn_result: str = ""       # e.g. "TD", "PUNT", "INT", "END OF HALF"

    # Computed result — set by rules engine
    result: DriveResult | None = None

    @property
    def label(self) -> str:
        return f"{self.team.full_name} Drive {self.team_drive_number}"

    @property
    def scrimmage_plays(self) -> list[Play]:
        return [p for p in self.plays if p.is_scrimmage_play]

    @property
    def scoring_plays(self) -> list[Play]:
        return [p for p in self.plays if p.is_scoring]

    @property
    def max_yardline_reached(self) -> int:
        """Minimum yards-to-endzone reached (closest to scoring)."""
        if not self.plays:
            return self.start_yardline
        # Lower yardsToEndzone = further into opponent territory
        endpoints = [p.end_yard_line for p in self.plays if p.end_yard_line > 0]
        return min(endpoints) if endpoints else self.start_yardline

    @property
    def is_touchdown(self) -> bool:
        return any(p.is_touchdown for p in self.plays)

    @property
    def is_passing_td(self) -> bool:
        return any(p.play_type == PlayType.PASSING_TD for p in self.plays)

    @property
    def is_rushing_td(self) -> bool:
        return any(p.play_type == PlayType.RUSHING_TD for p in self.plays)
