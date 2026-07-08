"""
Play-level markets — all are per-drive boolean questions.

NFL-only markets: 20+ Yard Passing Play, 10+ Yard Rushing Play, 20+ Yard Play
Universal:        Sack This Drive, Punt Fair Catch
"""
from __future__ import annotations
from models.drive import Drive, DriveResultGranular
from models.play import Play, PlayType


# ------------------------------------------------------------------ #
# Sack
# ------------------------------------------------------------------ #

def had_sack(drive: Drive) -> bool:
    """Was there at least one sack on this drive?"""
    return any(p.play_type == PlayType.SACK for p in drive.plays)


# ------------------------------------------------------------------ #
# Explosive play markets (NFL only)
# ------------------------------------------------------------------ #

def had_20_plus_passing_play(drive: Drive) -> bool:
    """
    Was there a passing play that gained 20+ yards?
    Includes passing TDs. Uses statYardage from ESPN.
    Sacks are negative passing plays — excluded by yards >= 20 check.
    """
    for play in drive.plays:
        if play.play_type in (
            PlayType.PASS_COMPLETE,
            PlayType.PASSING_TD,
        ) and play.yards >= 20:
            return True
    return False


def had_10_plus_rushing_play(drive: Drive) -> bool:
    """
    Was there a rushing play that gained 10+ yards?
    Includes rushing TDs.
    """
    for play in drive.plays:
        if play.play_type in (
            PlayType.RUSH,
            PlayType.RUSHING_TD,
        ) and play.yards >= 10:
            return True
    return False


def had_20_plus_play(drive: Drive) -> bool:
    """
    Was there any offensive play (pass or rush) that gained 20+ yards?
    Implication from workbook: if had_20_plus_passing_play=True then had_20_plus_play=True.
    """
    for play in drive.plays:
        if play.play_type in (
            PlayType.PASS_COMPLETE,
            PlayType.PASSING_TD,
            PlayType.RUSH,
            PlayType.RUSHING_TD,
        ) and play.yards >= 20:
            return True
    return False


# ------------------------------------------------------------------ #
# Punt Fair Catch
# ------------------------------------------------------------------ #

def punt_fair_catch(drive: Drive) -> bool | None:
    """
    Was there a fair catch on the punt that ended this drive?
    Returns:
      True  — punt with fair catch
      False — punt, no fair catch
      None  — N/A (drive did not end in a punt)

    ESPN does not have a dedicated fair catch play type.
    We detect it from the play description text on punt return plays.
    """
    if not drive.result:
        return None
    if drive.result.granular != DriveResultGranular.PUNT:
        return None  # N/A for non-punt drives

    # Look for punt return or fair catch signal in plays
    for play in reversed(drive.plays):
        desc = play.description.lower()
        if play.play_type == PlayType.PUNT or "punt" in desc:
            if "fair catch" in desc:
                return True
            if "no return" in desc or "touchback" in desc:
                return False
            # Punt with return yardage text = no fair catch
            if "return" in desc and "fair catch" not in desc:
                return False
            # Punt out of bounds = no fair catch
            if "out of bounds" in desc or "ob at" in desc:
                return False
    return None  # Could not determine


# ------------------------------------------------------------------ #
# Fourth down conversion (NFL only)
# ------------------------------------------------------------------ #

def converted_fourth_down(drive: Drive) -> bool:
    """
    Did the offense convert a 4th down attempt this drive?
    A conversion occurs when down=4 and the next play has a new set of downs
    (down resets to 1) or the drive ends in a score.
    """
    plays = drive.plays
    for i, play in enumerate(plays):
        if play.down != 4:
            continue
        if play.play_type in (PlayType.PUNT, PlayType.FIELD_GOAL_GOOD,
                               PlayType.FIELD_GOAL_MISSED, PlayType.FIELD_GOAL_BLOCKED):
            continue  # Intentional kicks on 4th — not a conversion attempt
        # Scoring play on 4th down = conversion
        if play.is_scoring:
            return True
        # Check if next play resets to 1st down (conversion)
        if i + 1 < len(plays):
            next_play = plays[i + 1]
            if next_play.down == 1 and next_play.play_type not in (
                PlayType.PENALTY, PlayType.TIMEOUT, PlayType.END_PERIOD,
                PlayType.END_OF_HALF, PlayType.END_OF_GAME,
            ):
                return True
    return False
