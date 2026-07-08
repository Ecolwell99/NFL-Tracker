"""
Rules engine entry point.

evaluate_drive() is the single function the rest of the application calls.
It runs every market rule against a normalized Drive and returns a
DriveMarketValues containing all computed results plus any warnings.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from models.drive import Drive, DriveResultGranular
from models.game import League
from rules.drive_result import compute_drive_result
from rules.yardlines import crossed_midfield, crossed_opp_35, crossed_opp_20
from rules.plays import (
    had_sack,
    had_20_plus_passing_play,
    had_10_plus_rushing_play,
    had_20_plus_play,
    punt_fair_catch,
    converted_fourth_down,
)
from rules.scoring import td_scorer_display, pass_catchers_display
from rules.validators import DriveMarketValues, validate_drive, validate_completeness


@dataclass
class EvaluatedDrive:
    drive_id: str
    drive_label: str
    team_abbrev: str
    team_drive_number: int
    sequence: int

    # Core result
    result_granular: str
    result_exact: str
    result_grouped: str

    # Yard-line markets
    cross_50: bool
    opp_35: bool
    opp_20: bool

    # Play markets
    sack: bool
    fair_catch: bool | None     # None = N/A

    # NFL-only play markets
    passing_20_plus: bool | None
    rushing_10_plus: bool | None
    play_20_plus: bool | None
    fourth_down_conversion: bool | None

    # Scoring
    td_scorer: str              # "N/A", player name, or "" if missing
    pass_catchers: str          # NFL only, may be ""

    # Meta
    is_nfl: bool
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return len(self.missing_fields) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def bool_display(self, value: bool | None) -> str:
        """Convert bool/None to workbook-style display string."""
        if value is True:
            return "Yes"
        if value is False:
            return "No"
        return "N/A"


def evaluate_drive(drive: Drive, league: League = League.NFL) -> EvaluatedDrive:
    """
    Run the full rules engine against a single Drive.
    This is the only function the UI and QC comparator need to call.
    """
    is_nfl = league == League.NFL

    # Ensure result is computed
    result = compute_drive_result(drive)
    granular = result.granular

    # Yard-line markets
    c50 = crossed_midfield(drive)
    o35 = crossed_opp_35(drive)
    o20 = crossed_opp_20(drive)

    # Play markets
    sack = had_sack(drive)
    fair_catch = punt_fair_catch(drive)

    # NFL-only markets
    p20 = had_20_plus_passing_play(drive) if is_nfl else None
    r10 = had_10_plus_rushing_play(drive) if is_nfl else None
    pl20 = had_20_plus_play(drive) if is_nfl else None
    fourth = converted_fourth_down(drive) if is_nfl else None

    # Scoring
    scorer_display = td_scorer_display(drive)
    catchers_display = pass_catchers_display(drive) if is_nfl else ""

    # Validate
    market_values = DriveMarketValues(
        granular=granular,
        exact=result.exact,
        grouped=result.grouped,
        cross_50=c50,
        opp_35=o35,
        opp_20=o20,
        sack=sack,
        fair_catch=fair_catch,
        td_scorer=scorer_display,
        passing_20_plus=p20,
        rushing_10_plus=r10,
        play_20_plus=pl20,
        fourth_down_conversion=fourth,
        is_nfl=is_nfl,
    )
    warnings = validate_drive(market_values)
    missing = validate_completeness(market_values)

    return EvaluatedDrive(
        drive_id=drive.drive_id,
        drive_label=drive.label,
        team_abbrev=drive.team.abbreviation,
        team_drive_number=drive.team_drive_number,
        sequence=drive.sequence,
        result_granular=granular.value,
        result_exact=result.exact.value,
        result_grouped=result.grouped.value,
        cross_50=c50,
        opp_35=o35,
        opp_20=o20,
        sack=sack,
        fair_catch=fair_catch,
        passing_20_plus=p20,
        rushing_10_plus=r10,
        play_20_plus=pl20,
        fourth_down_conversion=fourth,
        td_scorer=scorer_display,
        pass_catchers=catchers_display,
        is_nfl=is_nfl,
        warnings=warnings,
        missing_fields=missing,
    )


def evaluate_all_drives(drives: list[Drive], league: League = League.NFL) -> list[EvaluatedDrive]:
    """Evaluate every drive in a game. Returns results in original sequence order."""
    return [evaluate_drive(d, league) for d in drives]
