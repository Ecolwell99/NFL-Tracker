from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class PlayType(Enum):
    RUSH = "Rush"
    PASS_COMPLETE = "Pass Reception"
    PASS_INCOMPLETE = "Pass Incompletion"
    PASSING_TD = "Passing Touchdown"
    RUSHING_TD = "Rushing Touchdown"
    SACK = "Sack"
    INTERCEPTION = "Pass Interception Return"
    FUMBLE = "Fumble"
    PUNT = "Punt"
    PUNT_RETURN = "Punt Return"
    KICKOFF = "Kickoff"
    KICKOFF_RETURN = "Kickoff Return"
    FIELD_GOAL_GOOD = "Field Goal Good"
    FIELD_GOAL_MISSED = "Field Goal Missed"
    FIELD_GOAL_BLOCKED = "Field Goal Blocked"
    EXTRA_POINT_GOOD = "Extra Point Good"
    EXTRA_POINT_MISSED = "Extra Point Missed"
    TWO_POINT_CONVERSION = "Two Point Conversion"
    PENALTY = "Penalty"
    TIMEOUT = "Timeout"
    END_PERIOD = "End Period"
    END_OF_HALF = "End of Half"
    END_OF_GAME = "End of Game"
    FOURTH_DOWN_CONVERSION = "Fourth Down Conversion"
    FAIR_CATCH = "Fair Catch"
    UNKNOWN = "Unknown"

    @classmethod
    def from_espn_id(cls, type_id: str, text: str = "") -> PlayType:
        _ESPN_ID_MAP = {
            "5": cls.RUSH,
            "24": cls.PASS_COMPLETE,
            "3": cls.PASS_INCOMPLETE,
            "67": cls.PASSING_TD,
            "68": cls.RUSHING_TD,
            "7": cls.SACK,
            "26": cls.INTERCEPTION,
            "52": cls.PUNT,
            "53": cls.KICKOFF,
            "59": cls.FIELD_GOAL_GOOD,
            "60": cls.FIELD_GOAL_MISSED,
            "61": cls.FIELD_GOAL_BLOCKED,
            "2": cls.END_PERIOD,
            "65": cls.END_OF_HALF,
            "66": cls.END_OF_GAME,
            "8": cls.PENALTY,
            "21": cls.TIMEOUT,
            "74": cls.TIMEOUT,
            "75": cls.TIMEOUT,
        }
        play_type = _ESPN_ID_MAP.get(str(type_id), cls.UNKNOWN)
        # Resolve UNKNOWN cases from text
        if play_type == cls.UNKNOWN and text:
            t = text.lower()
            if "fair catch" in t:
                return cls.FAIR_CATCH
            if "field goal" in t and ("no good" in t or "missed" in t or "blocked" in t):
                return cls.FIELD_GOAL_MISSED
            if "fumble" in t:
                return cls.FUMBLE
        return play_type


@dataclass
class Player:
    player_id: str
    display_name: str
    position: str = ""

    def __hash__(self):
        return hash(self.player_id)


@dataclass
class Play:
    play_id: str
    sequence: int
    play_type: PlayType
    yards: int                      # statYardage — yards gained on this play
    down: int                       # 1-4, 0 if N/A
    distance: int                   # yards to go
    yard_line: int                  # 0-100 normalized (yards to endzone)
    end_yard_line: int              # yards to endzone at end of play
    description: str
    is_scoring: bool = False
    is_penalty: bool = False
    penalty_accepted: bool = False
    period: int = 1
    clock: str = ""
    athletes: list[Player] = field(default_factory=list)

    @property
    def is_pass(self) -> bool:
        return self.play_type in (
            PlayType.PASS_COMPLETE,
            PlayType.PASS_INCOMPLETE,
            PlayType.PASSING_TD,
            PlayType.INTERCEPTION,
        )

    @property
    def is_rush(self) -> bool:
        return self.play_type in (PlayType.RUSH, PlayType.RUSHING_TD)

    @property
    def is_touchdown(self) -> bool:
        return self.play_type in (PlayType.PASSING_TD, PlayType.RUSHING_TD)

    @property
    def is_sack(self) -> bool:
        return self.play_type == PlayType.SACK

    @property
    def is_scrimmage_play(self) -> bool:
        """Offensive plays that gain/lose real yards — excludes ST, penalties, TOs."""
        return self.play_type in (
            PlayType.RUSH,
            PlayType.RUSHING_TD,
            PlayType.PASS_COMPLETE,
            PlayType.PASS_INCOMPLETE,
            PlayType.PASSING_TD,
            PlayType.SACK,
            PlayType.INTERCEPTION,
        )
