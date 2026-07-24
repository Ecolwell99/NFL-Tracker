"""
Stat Correction Monitor — detects when ESPN data changes between refresh cycles.

Pattern mirrors the NHL tool's snapshot comparison (previous_sog_event_ids,
previous_faceoff_teams) but applied at the drive and play level with
market impact analysis.

On each refresh:
  1. Take a snapshot of current drives/plays
  2. Diff against the stored snapshot
  3. Any change = StatCorrection event
  4. Determine which markets are impacted
  5. Store in session state for the Corrections tab
"""
from __future__ import annotations
from dataclasses import dataclass, field
from models.drive import Drive, DriveResultGranular
from models.play import Play


# ------------------------------------------------------------------ #
# Data structures
# ------------------------------------------------------------------ #

@dataclass
class StatCorrection:
    detected_at: str            # ISO timestamp string
    drive_id: str
    drive_label: str
    field: str                  # what changed e.g. "Drive Result", "Play Yards"
    previous_value: str
    new_value: str
    markets_impacted: list[str] = field(default_factory=list)
    play_description: str = ""  # for play-level corrections


# ------------------------------------------------------------------ #
# Snapshot builders
# ------------------------------------------------------------------ #

def snapshot_drive(drive: Drive) -> dict:
    """
    Build a flat, serialisable snapshot of a drive for diffing.
    Only fields that could change via ESPN stat correction are included.
    """
    return {
        "drive_id":    drive.drive_id,
        "espn_result": drive.espn_result,
        "yards":       drive.yards_gained,
        "play_count":  drive.play_count,
        "start_yl":    drive.start_yardline,
        "end_yl":      drive.end_yardline,
        "plays":       {p.play_id: snapshot_play(p) for p in drive.plays},
    }


def snapshot_play(play: Play) -> dict:
    return {
        "play_id":     play.play_id,
        "type":        play.play_type.value,
        "yards":       play.yards,
        "down":        play.down,
        "yard_line":   play.yard_line,
        "end_yl":      play.end_yard_line,
        "scoring":     play.is_scoring,
        "description": play.description,
        "athletes":    [a.display_name for a in play.athletes],
    }


def snapshot_all_drives(drives: list[Drive]) -> dict[str, dict]:
    """Build snapshot dict: drive_id → drive snapshot."""
    return {d.drive_id: snapshot_drive(d) for d in drives}


# ------------------------------------------------------------------ #
# Market impact mapping
# ------------------------------------------------------------------ #

_DRIVE_RESULT_MARKETS = [
    "Drive Result Granular",
    "Drive Result Exact",
    "Drive Result Grouped",
]

_YARDLINE_MARKETS = [
    "Drive Crosses 50",
    "Drive Crosses Opposing 35",
    "Drive Crosses Opposing 20",
]

_EXPLOSIVE_PLAY_MARKETS = [
    "20+ Yard Passing Play",
    "10+ Yard Rushing Play",
    "20+ Yard Play",
]


def _markets_impacted_by_drive_change(field: str) -> list[str]:
    if field == "espn_result":
        return _DRIVE_RESULT_MARKETS
    if field in ("start_yl", "end_yl", "yards"):
        return _YARDLINE_MARKETS
    return ["Drive Result Granular"]


def _crosses(prev_yards: int, curr_yards: int, line: float) -> bool:
    """
    True if a yardage revision moved the play across `line` (an Over/Under
    threshold). Straddle test: one side under, the other over.
    """
    return (prev_yards <= line) != (curr_yards <= line)


def _markets_impacted_by_play_change(
    field: str,
    play_snap: dict,
    prev_snap: dict | None = None,
    is_nfl: bool = True,
) -> list[str]:
    play_type = play_snap.get("type", "")
    markets = []

    if field == "type":
        markets += _DRIVE_RESULT_MARKETS
        markets += _EXPLOSIVE_PLAY_MARKETS

    if field == "yards":
        yards = int(play_snap.get("yards", 0))
        prev_yards = int(prev_snap.get("yards", 0)) if prev_snap else yards
        is_rush = play_type in ("Rush", "Rushing Touchdown")
        is_catch = play_type in ("Pass Reception", "Passing Touchdown")

        # All per-play yardage markets are NFL-only and fire on exact crossing
        # only. No yardline markets here: a single play's yardage can't move a
        # drive-crossing market — that's caught by the drive-level yards /
        # start_yl / end_yl diff, which maps to the yardline markets.
        if is_nfl:
            if is_catch and _crosses(prev_yards, yards, 19.5):
                markets += ["20+ Yard Passing Play"]
            if (is_rush or is_catch) and _crosses(prev_yards, yards, 19.5):
                markets += ["20+ Yard Play"]
            if is_rush and _crosses(prev_yards, yards, 9.5):
                markets += ["10+ Yard Rushing Play"]
            if is_rush and _crosses(prev_yards, yards, 3.5):
                markets += ["Rusher Over 3.5 Yards"]
            if is_catch and _crosses(prev_yards, yards, 9.5):
                markets += ["Next Catch Over 9.5 Yards"]

    if field in ("yard_line", "end_yl"):
        markets += _YARDLINE_MARKETS

    if field == "athletes":
        markets += ["TD Scorer"]

    if field == "scoring":
        markets += _DRIVE_RESULT_MARKETS + ["TD Scorer"]

    return list(dict.fromkeys(markets))  # dedupe, preserve order


# ------------------------------------------------------------------ #
# Diff engine
# ------------------------------------------------------------------ #

def diff_drives(
    previous: dict[str, dict],
    current: dict[str, dict],
    drive_labels: dict[str, str],
    detected_at: str,
    is_nfl: bool = True,
) -> list[StatCorrection]:
    """
    Compare previous snapshot against current snapshot.
    Returns list of StatCorrection events (empty = no changes).

    Args:
        previous:     snapshot_all_drives() from last refresh cycle
        current:      snapshot_all_drives() from this refresh cycle
        drive_labels: drive_id → display label (for human-readable output)
        detected_at:  timestamp string e.g. "12:34:05 PM ET"
        is_nfl:       gates NFL-only micro-market thresholds
                      (Rusher Over 3.5 Yards, Next Catch Over 9.5 Yards)
    """
    corrections: list[StatCorrection] = []

    for drive_id, curr_snap in current.items():
        label = drive_labels.get(drive_id, drive_id)

        if drive_id not in previous:
            # New drive appeared — not a correction, just new data
            continue

        prev_snap = previous[drive_id]

        # ── Drive-level fields ────────────────────────────────────────
        for field in ("espn_result", "yards", "start_yl", "end_yl"):
            prev_val = str(prev_snap.get(field, ""))
            curr_val = str(curr_snap.get(field, ""))
            if prev_val != curr_val and prev_val and curr_val:
                corrections.append(StatCorrection(
                    detected_at=detected_at,
                    drive_id=drive_id,
                    drive_label=label,
                    field=_field_display_name(field),
                    previous_value=prev_val,
                    new_value=curr_val,
                    markets_impacted=_markets_impacted_by_drive_change(field),
                ))

        # ── Play-level fields ─────────────────────────────────────────
        prev_plays = prev_snap.get("plays", {})
        curr_plays = curr_snap.get("plays", {})

        # Removed plays
        for play_id in prev_plays:
            if play_id not in curr_plays:
                p = prev_plays[play_id]
                corrections.append(StatCorrection(
                    detected_at=detected_at,
                    drive_id=drive_id,
                    drive_label=label,
                    field="Play Removed",
                    previous_value=f"{p.get('type', '?')} {p.get('yards', '?')}yds",
                    new_value="(removed)",
                    markets_impacted=_DRIVE_RESULT_MARKETS + _YARDLINE_MARKETS + _EXPLOSIVE_PLAY_MARKETS,
                    play_description=p.get("description", "")[:100],
                ))

        # Changed plays
        for play_id, curr_play in curr_plays.items():
            if play_id not in prev_plays:
                continue
            prev_play = prev_plays[play_id]
            for field in ("type", "yards", "yard_line", "end_yl", "scoring", "athletes"):
                pv = prev_play.get(field)
                cv = curr_play.get(field)
                if pv != cv and pv is not None and cv is not None:
                    corrections.append(StatCorrection(
                        detected_at=detected_at,
                        drive_id=drive_id,
                        drive_label=label,
                        field=_play_field_display_name(field),
                        previous_value=str(pv),
                        new_value=str(cv),
                        markets_impacted=_markets_impacted_by_play_change(
                            field, curr_play, prev_play, is_nfl
                        ),
                        play_description=curr_play.get("description", "")[:100],
                    ))

    return corrections


def _field_display_name(field: str) -> str:
    return {
        "espn_result": "Drive Result",
        "yards":       "Drive Yards",
        "start_yl":    "Start Field Position",
        "end_yl":      "End Field Position",
        "play_count":  "Play Count",
    }.get(field, field)


def _play_field_display_name(field: str) -> str:
    return {
        "type":        "Play Type",
        "yards":       "Play Yards",
        "yard_line":   "Field Position (Start)",
        "end_yl":      "Field Position (End)",
        "scoring":     "Scoring Play Flag",
        "athletes":    "Players Involved",
        "description": "Play Description",
    }.get(field, field)


# ------------------------------------------------------------------ #
# Session-state helpers (used by app.py / state layer)
# ------------------------------------------------------------------ #

def build_drive_label_map(drives: list[Drive]) -> dict[str, str]:
    return {d.drive_id: d.label for d in drives}


def merge_corrections(
    existing: list[StatCorrection],
    new_corrections: list[StatCorrection],
    max_history: int = 200,
) -> list[StatCorrection]:
    """Append new corrections to the running log, capped at max_history."""
    merged = existing + new_corrections
    return merged[-max_history:]
