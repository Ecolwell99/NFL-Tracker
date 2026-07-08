"""
Drive Result rules — three-tier hierarchy from the workbook.

Granular: most specific (9 values, primary input)
Exact:    simplified (TD / FG / Punt / Turnover / Void)
Grouped:  binary + void (Offensive Score / No Offensive Score / Void)
"""
from __future__ import annotations
from models.drive import Drive, DriveResult, DriveResultGranular, DriveResultExact, DriveResultGrouped
from models.play import PlayType


_GRANULAR_TO_EXACT: dict[DriveResultGranular, DriveResultExact] = {
    DriveResultGranular.RUSHING_TD:                  DriveResultExact.TD,
    DriveResultGranular.PASSING_TD:                  DriveResultExact.TD,
    DriveResultGranular.FG_MADE:                     DriveResultExact.FG,
    DriveResultGranular.FG_MISSED:                   DriveResultExact.FG,
    DriveResultGranular.PUNT:                        DriveResultExact.PUNT,
    DriveResultGranular.TURNOVER_ON_DOWNS_OR_SAFETY: DriveResultExact.TURNOVER,
    DriveResultGranular.INTERCEPTION:                DriveResultExact.TURNOVER,
    DriveResultGranular.FUMBLE:                      DriveResultExact.TURNOVER,
    DriveResultGranular.END_OF_HALF:                 DriveResultExact.VOID,
}

_GRANULAR_TO_GROUPED: dict[DriveResultGranular, DriveResultGrouped] = {
    DriveResultGranular.RUSHING_TD:                  DriveResultGrouped.OFFENSIVE_SCORE,
    DriveResultGranular.PASSING_TD:                  DriveResultGrouped.OFFENSIVE_SCORE,
    DriveResultGranular.FG_MADE:                     DriveResultGrouped.OFFENSIVE_SCORE,
    DriveResultGranular.FG_MISSED:                   DriveResultGrouped.NO_OFFENSIVE_SCORE,
    DriveResultGranular.PUNT:                        DriveResultGrouped.NO_OFFENSIVE_SCORE,
    DriveResultGranular.TURNOVER_ON_DOWNS_OR_SAFETY: DriveResultGrouped.NO_OFFENSIVE_SCORE,
    DriveResultGranular.INTERCEPTION:                DriveResultGrouped.NO_OFFENSIVE_SCORE,
    DriveResultGranular.FUMBLE:                      DriveResultGrouped.NO_OFFENSIVE_SCORE,
    DriveResultGranular.END_OF_HALF:                 DriveResultGrouped.VOID,
}


def drive_result_exact(granular: DriveResultGranular) -> DriveResultExact:
    return _GRANULAR_TO_EXACT.get(granular, DriveResultExact.UNKNOWN)


def drive_result_grouped(granular: DriveResultGranular) -> DriveResultGrouped:
    return _GRANULAR_TO_GROUPED.get(granular, DriveResultGrouped.UNKNOWN)


def infer_granular_from_plays(drive: Drive) -> DriveResultGranular:
    """
    Infer drive result granular from play types when ESPN result string is ambiguous.
    Walks plays in reverse to find the terminal play.
    """
    for play in reversed(drive.plays):
        if play.play_type == PlayType.PASSING_TD:
            return DriveResultGranular.PASSING_TD
        if play.play_type == PlayType.RUSHING_TD:
            return DriveResultGranular.RUSHING_TD
        if play.play_type == PlayType.FIELD_GOAL_GOOD:
            return DriveResultGranular.FG_MADE
        if play.play_type == PlayType.FIELD_GOAL_MISSED:
            return DriveResultGranular.FG_MISSED
        if play.play_type == PlayType.FIELD_GOAL_BLOCKED:
            return DriveResultGranular.FG_MISSED
        if play.play_type == PlayType.PUNT:
            return DriveResultGranular.PUNT
        if play.play_type == PlayType.INTERCEPTION:
            return DriveResultGranular.INTERCEPTION
        if play.play_type in (PlayType.END_OF_HALF, PlayType.END_OF_GAME):
            return DriveResultGranular.END_OF_HALF
    return DriveResultGranular.UNKNOWN


def compute_drive_result(drive: Drive) -> DriveResult:
    """
    Produce the complete three-tier DriveResult for a drive.
    Uses the ESPN-resolved result if available, falls back to play inference.
    """
    granular = drive.result.granular if drive.result else DriveResultGranular.UNKNOWN

    if granular == DriveResultGranular.UNKNOWN:
        granular = infer_granular_from_plays(drive)

    return DriveResult(
        granular=granular,
        exact=drive_result_exact(granular),
        grouped=drive_result_grouped(granular),
    )
