"""
Scoring markets — TD scorer identification.

TD Scorer rules from workbook:
  - N/A on any non-TD drive result
  - Required (cannot be blank) on Rushing TD or Passing TD drives
  - Free text in the workbook; here we extract from ESPN play data

ESPN athlete ordering on scoring plays:
  Passing TD: athletes[0] = passer, athletes[1] = receiver
  Rushing TD: athletes[0] = rusher
"""
from __future__ import annotations
from models.drive import Drive, DriveResultGranular
from models.play import Play, PlayType, Player


def td_scorer(drive: Drive) -> Player | None:
    """
    Return the player who scored the touchdown on this drive.
    Returns None if the drive is not a TD or scorer cannot be determined.

    For passing TDs: returns the receiver (the player who crossed the goal line).
    For rushing TDs: returns the rusher.
    """
    if not drive.result:
        return None
    if drive.result.granular not in (DriveResultGranular.PASSING_TD, DriveResultGranular.RUSHING_TD):
        return None

    for play in reversed(drive.plays):
        if play.play_type == PlayType.PASSING_TD:
            if len(play.athletes) >= 2:
                return play.athletes[1]
            if len(play.athletes) == 1:
                return play.athletes[0]
            # Fallback: parse receiver from description e.g. "S.Darnold pass ... to A.Barner for"
            name = _parse_receiver_from_text(play.description)
            if name:
                return Player(player_id="", display_name=name)

        if play.play_type == PlayType.RUSHING_TD:
            if play.athletes:
                return play.athletes[0]
            # Fallback: parse rusher from description e.g. "A.Jones up the middle for ... TOUCHDOWN"
            name = _parse_rusher_from_text(play.description)
            if name:
                return Player(player_id="", display_name=name)

    return None


def td_passer(drive: Drive) -> Player | None:
    """
    Return the quarterback who threw the touchdown pass.
    Returns None if not a passing TD drive.
    """
    if not drive.result:
        return None
    if drive.result.granular != DriveResultGranular.PASSING_TD:
        return None

    for play in reversed(drive.plays):
        if play.play_type == PlayType.PASSING_TD:
            if play.athletes:
                return play.athletes[0]
            name = _parse_passer_from_text(play.description)
            if name:
                return Player(player_id="", display_name=name)

    return None


def td_scorer_display(drive: Drive) -> str:
    """
    Return a display string for the TD scorer, matching workbook format.
    Examples:
      "Mike Evans (pass from Mayfield)"
      "Sean Tucker"
      "N/A"
    """
    if not drive.result:
        return "N/A"
    if drive.result.granular not in (DriveResultGranular.PASSING_TD, DriveResultGranular.RUSHING_TD):
        return "N/A"

    scorer = td_scorer(drive)
    if not scorer:
        return ""  # Missing — triggers warning

    if drive.result.granular == DriveResultGranular.PASSING_TD:
        passer = td_passer(drive)
        if passer:
            passer_last = passer.display_name.split()[-1] if passer.display_name else ""
            return f"{scorer.display_name} (pass from {passer_last})"
        return scorer.display_name

    return scorer.display_name  # Rushing TD


def pass_catchers_display(drive: Drive) -> str:
    """
    NFL only. Comma-separated list of all players who caught passes this drive.
    Format mirrors workbook Pass Catchers row (free text, no dropdown).
    """
    catchers: list[str] = []
    seen: set[str] = set()

    for play in drive.plays:
        if play.play_type in (PlayType.PASS_COMPLETE, PlayType.PASSING_TD):
            # athletes[1] = receiver for complete passes
            if len(play.athletes) >= 2:
                receiver = play.athletes[1]
                # Use last name only to match workbook style (e.g. "M. Evans")
                name = _abbreviated_name(receiver.display_name)
                if name and name not in seen:
                    catchers.append(name)
                    seen.add(name)

    return ", ".join(catchers) if catchers else ""


def pass_catchers_table(drive: Drive) -> list[dict]:
    """
    NFL only. Per-receiver receptions and receiving yards for this drive.
    Returns rows [{"Player": "M. Evans", "Rec": 2, "Yds": 34}, ...] ordered
    by yards descending. Empty list if no completed passes on the drive.

    Yards use ESPN statYardage (air + YAC) — the standard receiving-yards
    figure, so it matches a box score.
    """
    order: list[str] = []
    tally: dict[str, dict] = {}

    for play in drive.plays:
        if play.play_type not in (PlayType.PASS_COMPLETE, PlayType.PASSING_TD):
            continue

        # athletes[1] = receiver on a completion; fall back to description text
        name = ""
        if len(play.athletes) >= 2:
            name = _abbreviated_name(play.athletes[1].display_name)
        else:
            parsed = _parse_receiver_from_text(play.description)
            if parsed:
                name = parsed  # already in "A.Barner" ESPN short form
        if not name:
            continue

        if name not in tally:
            tally[name] = {"Player": name, "Rec": 0, "Yds": 0}
            order.append(name)
        tally[name]["Rec"] += 1
        tally[name]["Yds"] += int(play.yards or 0)

    rows = [tally[n] for n in order]
    rows.sort(key=lambda r: r["Yds"], reverse=True)
    return rows


def _abbreviated_name(full_name: str) -> str:
    """Convert 'Mike Evans' → 'M. Evans' to match workbook style."""
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0][0]}. {' '.join(parts[1:])}"
    return full_name


import re as _re

def _parse_passer_from_text(text: str) -> str:
    # "S.Darnold pass ..." → "S.Darnold"
    m = _re.match(r"([A-Z]\.\S+)\s+pass", text)
    return m.group(1) if m else ""


def _parse_receiver_from_text(text: str) -> str:
    # "... pass ... to A.Barner for" or "... pass ... intended for A.Barner"
    m = _re.search(r"pass\s+\S+(?:\s+\S+)?\s+to\s+([A-Z]\.\S+)", text)
    if m:
        return m.group(1)
    m = _re.search(r"intended\s+for\s+([A-Z]\.\S+)", text)
    return m.group(1) if m else ""


def _parse_rusher_from_text(text: str) -> str:
    # "A.Jones up the middle ..." → "A.Jones"
    m = _re.match(r"([A-Z]\.\S+)\s+", text)
    return m.group(1) if m else ""
