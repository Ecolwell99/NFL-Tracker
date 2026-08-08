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
from rules.yardlines import _min_yards_to_endzone


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

    # ── Filtering support (Corrections tab) ──────────────────────────
    # Team that owned the drive, e.g. "CAR". Carried explicitly rather than
    # regexed out of drive_label at render time.
    team_abbrev: str = ""
    # Play type string for play-level corrections, "" for drive-level ones.
    # Display/debug only — filtering uses play_classes.
    play_type: str = ""
    # Which play classes ("Rush" / "Pass") this correction touches, computed at
    # diff time so the UI never has to re-derive play semantics. A type change
    # lists BOTH sides: "Rush -> Fumble" yields ["Rush"] so a rush play being
    # reclassified still appears under a Rush filter — that is precisely the card
    # you most want to see. Empty for drive-level corrections.
    play_classes: list[str] = field(default_factory=list)


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
        # Furthest advance (min yards-to-endzone) straight from settlement logic
        # in rules/yardlines.py. Informational/debug only — the crossing test in
        # diff_drives recomputes this over the plays shared by both snapshots so
        # a drive merely advancing can't look like a correction.
        "min_yte":     _min_yards_to_endzone(drive),
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
    # Drive yards / start / end position changes are logged as informational
    # corrections. The yardline-crossing markets are NOT flagged here — they
    # fire only from the dedicated min_yte crossing test (see diff_drives),
    # which mirrors settlement: a market moves only when the drive's furthest
    # advance actually crosses that specific line.
    return []


def _crosses(prev_yards: int, curr_yards: int, line: float) -> bool:
    """
    True if a yardage revision moved the play across `line` (an Over/Under
    threshold). Straddle test: one side under, the other over.
    """
    return (prev_yards <= line) != (curr_yards <= line)


# Yards-to-endzone line for each crossing market. Ball must reach the opp
# 49/34/19 or closer to cross (strict <), so the straddle line sits at .5 below
# the threshold: crossing 50 => min_yte moves across 49.5, etc.
_YARDLINE_CROSS_TESTS = [
    (49.5, "Drive Crosses 50"),
    (34.5, "Drive Crosses Opposing 35"),
    (19.5, "Drive Crosses Opposing 20"),
]


def _yardline_markets_crossed(prev_min_yte: int, curr_min_yte: int) -> list[str]:
    """
    Which yardline-crossing markets flipped when a drive's furthest advance
    (min yards-to-endzone) was revised. A market fires only if the specific
    line was straddled. Lower yte = deeper into opponent territory, so a
    revision that *reduces* min_yte across a line = crossed it (Yes); one that
    *increases* it back across = un-crossed (also a real change to flag).
    """
    markets = []
    for line, market in _YARDLINE_CROSS_TESTS:
        if _crosses(prev_min_yte, curr_min_yte, line):
            markets.append(market)
    return markets


# Play type values that reach the endzone (mirrors Play.is_touchdown).
_TD_PLAY_TYPES = ("Passing Touchdown", "Rushing Touchdown")


def _min_yte_from_play_snaps(play_snaps: list[dict]) -> int | None:
    """
    Recompute furthest advance (min yards-to-endzone) from a set of play
    snapshots. Mirrors _min_yards_to_endzone in rules/yardlines.py: a TD play
    counts as 0, and non-positive endpoints are excluded (own endzone / missing
    data). Returns None when no play carries a usable position — there is then
    no basis for a before/after comparison.
    """
    endpoints: list[int] = []
    for snap in play_snaps:
        if snap.get("type") in _TD_PLAY_TYPES:
            return 0
        for key in ("end_yl", "yard_line"):
            val = snap.get(key)
            if isinstance(val, int) and val > 0:
                endpoints.append(val)
    return min(endpoints) if endpoints else None


# Kick/punt and return play types. A type change on one of these is a return
# event (e.g. ESPN appending "FUMB" to a punt when the returner fumbles) and is
# NOT logged as a correction — see the type loop in diff_drives. Field goals are
# deliberately absent: FG Good <-> Missed genuinely moves the drive result.
_ST_RETURN_TYPES = (
    "Punt",
    "Punt Return",
    "Kickoff",
    "Kickoff Return",
    "Fair Catch",
)


# ── Play classification for the Corrections tab filter ──────────────
# String-keyed on purpose: snapshots store play_type.value (a plain str) so they
# survive pickling through st.cache_data. Do NOT route this through
# Play.is_rush / Play.is_pass — those take a PlayType enum, not a string.
#
# DELIBERATE DIVERGENCE from Play.is_pass (models/play.py): SACK is classified
# here as a Pass. A sack is a dropback, so a trader filtering to Pass expects to
# see sack yardage revisions. Play.is_pass excludes SACK because it feeds yardage
# and market logic where a sack is not a pass attempt. Both are correct for their
# own purpose — this is not an oversight, and the two must not be "reconciled".
PLAY_CLASS_RUSH = "Rush"
PLAY_CLASS_PASS = "Pass"

_RUSH_TYPES = frozenset({"Rush", "Rushing Touchdown"})
_PASS_TYPES = frozenset({
    "Pass Reception",
    "Pass Incompletion",
    "Passing Touchdown",
    "Pass Interception Return",
    "Sack",                      # see divergence note above
})


def _play_class(play_type: str) -> str | None:
    """Rush / Pass bucket for a play type string, or None if it is neither."""
    if play_type in _RUSH_TYPES:
        return PLAY_CLASS_RUSH
    if play_type in _PASS_TYPES:
        return PLAY_CLASS_PASS
    return None


def _play_classes_for(*play_types: str) -> list[str]:
    """
    Classes touched by a correction. Pass every relevant type (both sides of a
    type change) so a reclassified play still matches its original class.
    Order-stable: Rush before Pass.
    """
    found = {c for pt in play_types if (c := _play_class(pt)) is not None}
    return [c for c in (PLAY_CLASS_RUSH, PLAY_CLASS_PASS) if c in found]


def _explosive_markets_satisfied(play_type: str, yards: int) -> set[str]:
    """
    Which explosive-play markets a single play would settle Yes on, given its
    type and yardage. Used to diff before/after a type revision so a market is
    only reported when the answer actually changes.
    """
    is_rush = play_type in ("Rush", "Rushing Touchdown")
    is_catch = play_type in ("Pass Reception", "Passing Touchdown")
    satisfied = set()
    if is_catch and yards >= 20:
        satisfied.add("20+ Yard Passing Play")
    if is_rush and yards >= 10:
        satisfied.add("10+ Yard Rushing Play")
    if (is_rush or is_catch) and yards >= 20:
        satisfied.add("20+ Yard Play")
    return satisfied


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
        # Explosive-play markets are NFL-only and were previously listed for ANY
        # type change regardless of yardage — a 7-yard play reclassified would
        # claim "20+ Yard Passing Play" was impacted. Report only markets whose
        # Yes/No answer actually differs between the old and new play type.
        if is_nfl:
            yards = int(play_snap.get("yards", 0) or 0)
            prev_type = prev_snap.get("type", "") if prev_snap else play_type
            before = _explosive_markets_satisfied(prev_type, yards)
            after = _explosive_markets_satisfied(play_type, yards)
            flipped = before ^ after  # symmetric difference = genuinely changed
            markets += [m for m in _EXPLOSIVE_PLAY_MARKETS if m in flipped]

    if field == "yards":
        yards = int(play_snap.get("yards", 0))
        prev_yards = int(prev_snap.get("yards", 0)) if prev_snap else yards
        is_rush = play_type in ("Rush", "Rushing Touchdown")
        is_catch = play_type in ("Pass Reception", "Passing Touchdown")

        # All per-play yardage markets are NFL-only and fire on exact crossing
        # only. No yardline markets here: a single play's yardage can't move a
        # drive-crossing market — that's caught by the drive-level Furthest
        # Advance (min_yte) crossing test.
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
    drive_teams: dict[str, str] | None = None,
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
        drive_teams:  drive_id → team abbreviation, for the Corrections tab team
                      filter. Optional so existing callers/tests keep working;
                      when omitted, team_abbrev is "" and the team filter simply
                      has nothing to match on.
    """
    corrections: list[StatCorrection] = []
    teams = drive_teams or {}

    for drive_id, curr_snap in current.items():
        label = drive_labels.get(drive_id, drive_id)
        team = teams.get(drive_id, "")

        if drive_id not in previous:
            # New drive appeared — not a correction, just new data
            continue

        prev_snap = previous[drive_id]

        # ── Drive-level fields ────────────────────────────────────────
        # Only the drive result is tracked here. Yardline crossing is handled by
        # the Furthest Advance test further down; drive total yards and start/end
        # position are intentionally NOT logged — they carry no market impact of
        # their own and duplicate the Furthest Advance card.
        for field in ("espn_result",):
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
                    team_abbrev=team,
                    # Drive-level: no play class. Hidden by a Rush/Pass filter.
                ))

        # ── Play-level fields ─────────────────────────────────────────
        prev_plays = prev_snap.get("plays", {})
        curr_plays = curr_snap.get("plays", {})

        # ── Yardline crossing (furthest advance) ──────────────────────
        # Fire a dedicated correction only for lines the drive's furthest
        # advance actually straddled — mirrors settlement in rules/yardlines.py.
        #
        # The comparison is restricted to plays present in BOTH snapshots. The
        # stored min_yte covers every play in its cycle, so a live drive simply
        # ADVANCING (new play snapped, ball now deeper) moved min_yte and was
        # reported as a stat correction — e.g. ARI on the CAR 40 gaining to the
        # CAR 25 flagged "Drive Crosses Opposing 35". That is normal play, not
        # ESPN revising history. Recomputing over the shared play set holds new
        # plays out of the test, so this fires only when ESPN actually changes
        # the position of a play it already reported.
        shared_ids = [pid for pid in curr_plays if pid in prev_plays]
        if shared_ids:
            prev_min = _min_yte_from_play_snaps([prev_plays[pid] for pid in shared_ids])
            curr_min = _min_yte_from_play_snaps([curr_plays[pid] for pid in shared_ids])
            if prev_min is not None and curr_min is not None and prev_min != curr_min:
                crossed = _yardline_markets_crossed(prev_min, curr_min)
                if crossed:
                    corrections.append(StatCorrection(
                        detected_at=detected_at,
                        drive_id=drive_id,
                        drive_label=label,
                        field="Furthest Advance",
                        previous_value=str(prev_min),
                        new_value=str(curr_min),
                        markets_impacted=crossed,
                        team_abbrev=team,
                        # Drive-level: derived from the whole shared play set, so
                        # no single play class applies. Hidden by a Rush/Pass
                        # filter — the tab warns when that happens.
                    ))

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
                    team_abbrev=team,
                    # Class comes from the removed play's own type (there is no
                    # "current" side), so a deleted rush still matches Rush.
                    play_type=str(p.get("type", "")),
                    play_classes=_play_classes_for(str(p.get("type", ""))),
                ))

        # Changed plays
        for play_id, curr_play in curr_plays.items():
            if play_id not in prev_plays:
                continue
            prev_play = prev_plays[play_id]
            # yard_line / end_yl deliberately excluded: a play's position change
            # is captured by the drive-level Furthest Advance test, so logging it
            # here would just duplicate that card (often as a market-less "None").
            for field in ("type", "yards", "scoring", "athletes"):
                pv = prev_play.get(field)
                cv = curr_play.get(field)
                if pv == cv or pv is None or cv is None:
                    continue
                # Skip type changes on kicks/returns. ESPN reclassifies a punt to
                # Fumble when the RETURNER fumbles (it appends "FUMB" to the punt
                # text), which read as "Carolina Drive 1 corrected Punt -> Fumble"
                # even though the punting team's drive result never changed and
                # the Drives tab still correctly showed Punt. A return event moves
                # no market for the drive's own team, so it is not a correction.
                if field == "type" and (
                    str(pv) in _ST_RETURN_TYPES or str(cv) in _ST_RETURN_TYPES
                ):
                    continue
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
                    team_abbrev=team,
                    play_type=str(curr_play.get("type", "")),
                    # BOTH sides: on a "Rush -> Fumble" type change the new type
                    # is neither class, so passing only the current type would
                    # drop the card from a Rush filter — exactly the card a
                    # trader is looking for. Non-type changes pass the same value
                    # twice, which the set collapses.
                    play_classes=_play_classes_for(
                        str(prev_play.get("type", "")),
                        str(curr_play.get("type", "")),
                    ),
                ))

    return corrections


def _field_display_name(field: str) -> str:
    return {
        "espn_result": "Drive Result",
        "yards":       "Drive Yards",
        "start_yl":    "Start Field Position",
        "end_yl":      "End Field Position",
        "play_count":  "Play Count",
        "min_yte":     "Furthest Advance",
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


def build_drive_team_map(drives: list[Drive]) -> dict[str, str]:
    """drive_id → team abbreviation, for the Corrections tab team filter."""
    return {d.drive_id: d.team.abbreviation for d in drives}


def merge_corrections(
    existing: list[StatCorrection],
    new_corrections: list[StatCorrection],
    max_history: int = 200,
) -> list[StatCorrection]:
    """Append new corrections to the running log, capped at max_history."""
    merged = existing + new_corrections
    return merged[-max_history:]
