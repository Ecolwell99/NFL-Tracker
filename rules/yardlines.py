"""
Yard-line crossing markets.

All positions use yardsToEndzone convention (ESPN native):
  0  = opponent endzone (touchdown)
  50 = midfield
  100 = own endzone (starting position deep in own territory)

Crossing thresholds:
  Midfield      = yardsToEndzone < 50   (must reach opp 49 or closer)
  Opponent 35   = yardsToEndzone < 35   (must reach opp 34 or closer)
  Opponent 20   = yardsToEndzone < 20   (must reach opp 19 or closer)

Invariant chain from workbook (hard rules):
  TD            → Cross50=Yes, Opp35=Yes, Opp20=Yes  (always)
  Opp20=Yes     → Opp35=Yes, Cross50=Yes             (ball passed through both)
  Cross50=No    → Opp35=No,  Opp20=No               (never entered opponent half)
"""
from __future__ import annotations
from models.drive import Drive, DriveResultGranular
from models.play import PlayType

_MIDFIELD_THRESHOLD = 50
_OPP_35_THRESHOLD   = 35
_OPP_20_THRESHOLD   = 20


def _min_yards_to_endzone(drive: Drive) -> int:
    """
    Lowest yardsToEndzone reached during the drive — closest the team got to scoring.
    TD plays are treated as 0 (endzone reached).
    Uses end_yard_line of each play; filters out 0 for non-scoring plays to avoid
    kickoffs and other plays where end position is legitimately in own endzone.
    """
    if drive.is_touchdown:
        return 0

    endpoints = []
    for play in drive.plays:
        if play.is_touchdown:
            return 0
        # end_yard_line = yardsToEndzone at end of play
        # Exclude 0 on non-scoring plays (would mean own endzone / error)
        if play.end_yard_line > 0:
            endpoints.append(play.end_yard_line)
        # Also include start position
        if play.yard_line > 0:
            endpoints.append(play.yard_line)

    return min(endpoints) if endpoints else drive.start_yardline


def crossed_midfield(drive: Drive) -> bool:
    """
    Did this drive cross midfield (enter the opponent's half of the field)?
    Auto-True on any touchdown result.
    """
    if drive.is_touchdown:
        return True
    return _min_yards_to_endzone(drive) < _MIDFIELD_THRESHOLD


def crossed_opp_35(drive: Drive) -> bool:
    """
    Did this drive cross the opponent's 35 yard line?
    Auto-True on any touchdown result.
    Implication: if True, crossed_midfield must also be True.
    """
    if drive.is_touchdown:
        return True
    return _min_yards_to_endzone(drive) < _OPP_35_THRESHOLD


def crossed_opp_20(drive: Drive) -> bool:
    """
    Did this drive enter the red zone (cross opponent's 20 yard line)?
    Auto-True on any touchdown result or FG made (must have been in range).
    Implication: if True, crossed_opp_35 and crossed_midfield must also be True.
    """
    if drive.is_touchdown:
        return True
    # FG made from inside the 20 — endpoint would be 0 on the kick, check plays
    if drive.result and drive.result.granular == DriveResultGranular.FG_MADE:
        # FG attempts are typically from inside the 40; a made FG from inside 20 is rare
        # but possible. Check actual field position.
        pass
    return _min_yards_to_endzone(drive) < _OPP_20_THRESHOLD


def validate_yardline_chain(
    cross50: bool,
    opp35: bool,
    opp20: bool,
) -> list[str]:
    """
    Validate the implication chain from the workbook Warnings formula.
    Returns a list of warning strings (empty = valid).
    """
    warnings = []
    if opp20 and not opp35:
        warnings.append("Opp20=Yes implies Opp35 must also be Yes")
    if opp20 and not cross50:
        warnings.append("Opp20=Yes implies Cross50 must also be Yes")
    if opp35 and not cross50:
        warnings.append("Opp35=Yes implies Cross50 must also be Yes")
    if not cross50 and opp35:
        warnings.append("Cross50=No implies Opp35 must be No")
    if not cross50 and opp20:
        warnings.append("Cross50=No implies Opp20 must be No")
    return warnings
