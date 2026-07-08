"""
Unit tests for the QC comparator and stat corrections engine.
No network calls, no Streamlit.
Run from nfl_qc_tool/: python -m pytest tests/test_qc.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.game import Team, League
from models.drive import Drive, DriveResult, DriveResultGranular, DriveResultExact, DriveResultGrouped
from models.play import Play, PlayType, Player
from rules.engine import evaluate_drive
from qc.status import QCStatus
from qc.comparator import compare_drive, compare_all_drives, get_all_mismatches, QCResult
from qc.corrections import (
    snapshot_drive, snapshot_all_drives, diff_drives,
    build_drive_label_map, merge_corrections, StatCorrection,
)

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

_TEAM = Team(id="27", name="Buccaneers", full_name="Tampa Bay Buccaneers",
             abbreviation="TB", color="#D50A0A")


def _drive_result(granular):
    from rules.drive_result import drive_result_exact, drive_result_grouped
    return DriveResult(
        granular=granular,
        exact=drive_result_exact(granular),
        grouped=drive_result_grouped(granular),
    )


def _play(play_type, yards=0, down=1, yard_line=65, end_yard_line=None,
          is_scoring=False, athletes=None, description=""):
    return Play(
        play_id=f"p_{play_type.value}_{yards}",
        sequence=1, play_type=play_type, yards=yards,
        down=down, distance=10,
        yard_line=yard_line,
        end_yard_line=end_yard_line if end_yard_line is not None else max(0, yard_line - yards),
        description=description, is_scoring=is_scoring,
        athletes=athletes or [],
    )


def _td_drive(drive_id="d1"):
    qb = Player("1", "Baker Mayfield")
    receiver = Player("2", "Mike Evans")
    plays = [
        _play(PlayType.RUSH, yards=10, yard_line=65, end_yard_line=55),
        _play(PlayType.PASS_COMPLETE, yards=25, yard_line=55, end_yard_line=30),
        _play(PlayType.PASSING_TD, yards=30, yard_line=30, end_yard_line=0,
              is_scoring=True, athletes=[qb, receiver]),
    ]
    return Drive(
        drive_id=drive_id, game_id="g1", sequence=1,
        team=_TEAM, team_drive_number=1,
        plays=plays,
        espn_result="TD",
        result=_drive_result(DriveResultGranular.PASSING_TD),
    )


def _punt_drive(drive_id="d2"):
    plays = [
        _play(PlayType.RUSH, yards=3, yard_line=80, end_yard_line=77),
        _play(PlayType.PASS_INCOMPLETE, yards=0, yard_line=77, end_yard_line=77),
        _play(PlayType.RUSH, yards=2, yard_line=77, end_yard_line=75),
        _play(PlayType.PUNT, yards=0, yard_line=75, end_yard_line=75,
              description="J.Hekker punts 48 yards. Fair catch by D.Adams at the 27."),
    ]
    return Drive(
        drive_id=drive_id, game_id="g1", sequence=2,
        team=_TEAM, team_drive_number=2,
        plays=plays,
        espn_result="PUNT",
        result=_drive_result(DriveResultGranular.PUNT),
    )


# ------------------------------------------------------------------ #
# Comparator — status logic
# ------------------------------------------------------------------ #

def test_match_when_system_equals_expected():
    drive = _td_drive()
    ev = evaluate_drive(drive, League.NFL)
    system = {
        "Drive Result Granular": "Passing TD",
        "Drive Result Exact":    "TD",
        "Drive Result Grouped":  "Offensive Score",
        "Drive Crosses 50":      "Yes",
        "Drive Crosses Opposing 35": "Yes",
        "Drive Crosses Opposing 20": "Yes",
        "Sack This Drive":       "No",
        "Punt Fair Catch":       "N/A",
        "20+ Yard Passing Play": "Yes",
        "10+ Yard Rushing Play": "Yes",
        "20+ Yard Play":         "Yes",
        "4th Down Conversion":   "No",
        "TD Scorer":             "Mike Evans (pass from Mayfield)",
    }
    dqc = compare_drive(ev, system)
    mismatches = [r for r in dqc.results if r.status == QCStatus.MISMATCH]
    assert mismatches == [], f"Unexpected mismatches: {[(r.market, r.expected, r.system) for r in mismatches]}"


def test_mismatch_on_wrong_drive_result():
    drive = _td_drive()
    ev = evaluate_drive(drive, League.NFL)
    system = {"Drive Result Granular": "Rushing TD"}  # wrong — should be Passing TD
    dqc = compare_drive(ev, system)
    mismatch = next(r for r in dqc.results if r.market == "Drive Result Granular")
    assert mismatch.status == QCStatus.MISMATCH
    assert mismatch.expected == "Passing TD"
    assert mismatch.system == "Rushing TD"


def test_pending_when_system_empty():
    drive = _punt_drive()
    ev = evaluate_drive(drive, League.NFL)
    dqc = compare_drive(ev, {})
    pending = [r for r in dqc.results if r.status == QCStatus.PENDING]
    assert len(pending) > 0


def test_case_insensitive_match():
    drive = _punt_drive()
    ev = evaluate_drive(drive, League.NFL)
    system = {"Drive Result Exact": "punt"}  # lowercase should still match
    dqc = compare_drive(ev, system)
    result = next(r for r in dqc.results if r.market == "Drive Result Exact")
    assert result.status == QCStatus.MATCH


def test_yes_no_aliases():
    drive = _td_drive()
    ev = evaluate_drive(drive, League.NFL)
    system = {"Drive Crosses 50": "yes"}  # lowercase
    dqc = compare_drive(ev, system)
    result = next(r for r in dqc.results if r.market == "Drive Crosses 50")
    assert result.status == QCStatus.MATCH


def test_na_status_for_fair_catch_on_td():
    drive = _td_drive()
    ev = evaluate_drive(drive, League.NFL)
    dqc = compare_drive(ev, {})
    fair_catch = next(r for r in dqc.results if r.market == "Punt Fair Catch")
    assert fair_catch.status in (QCStatus.NOT_APPLICABLE, QCStatus.PENDING)


def test_drive_qc_overall_status_mismatch():
    drive = _td_drive()
    ev = evaluate_drive(drive, League.NFL)
    system = {"Drive Result Granular": "Rushing TD"}  # one mismatch
    dqc = compare_drive(ev, system)
    assert dqc.overall_status == QCStatus.MISMATCH
    assert dqc.mismatch_count >= 1


def test_drive_qc_overall_status_pending():
    drive = _td_drive()
    ev = evaluate_drive(drive, League.NFL)
    dqc = compare_drive(ev, {})
    assert dqc.overall_status == QCStatus.PENDING


def test_get_all_mismatches():
    drives = [_td_drive("d1"), _punt_drive("d2")]
    from rules.engine import evaluate_all_drives
    evs = evaluate_all_drives(drives, League.NFL)
    system = {
        "d1": {"Drive Result Granular": "Rushing TD"},   # mismatch
        "d2": {},                                         # all pending
    }
    dqcs = compare_all_drives(evs, system)
    mismatches = get_all_mismatches(dqcs)
    assert len(mismatches) >= 1
    drive_ids = {dqc.drive_id for dqc, _ in mismatches}
    assert "d1" in drive_ids


# ------------------------------------------------------------------ #
# Stat corrections
# ------------------------------------------------------------------ #

def test_snapshot_drive_is_serialisable():
    drive = _td_drive()
    snap = snapshot_drive(drive)
    assert "espn_result" in snap
    assert "plays" in snap
    assert isinstance(snap["plays"], dict)


def test_no_corrections_when_unchanged():
    drive = _td_drive()
    snap = snapshot_all_drives([drive])
    corrections = diff_drives(snap, snap, {"d1": "TB Drive 1"}, "12:00:00")
    assert corrections == []


def test_correction_detected_on_drive_result_change():
    drive = _td_drive()
    prev = snapshot_all_drives([drive])

    # Simulate ESPN correcting the drive result
    drive.espn_result = "PUNT"
    curr = snapshot_all_drives([drive])

    corrections = diff_drives(prev, curr, {"d1": "TB Drive 1"}, "12:01:00")
    assert len(corrections) >= 1
    c = corrections[0]
    assert c.field == "Drive Result"
    assert c.previous_value == "TD"
    assert c.new_value == "PUNT"
    assert "Drive Result Granular" in c.markets_impacted


def test_correction_detected_on_play_yards_change():
    drive = _punt_drive()
    prev = snapshot_all_drives([drive])

    # Simulate ESPN correcting a rush play from 3 yards to 8 yards
    drive.plays[0].yards = 8
    curr = snapshot_all_drives([drive])

    corrections = diff_drives(prev, curr, {"d2": "TB Drive 2"}, "12:02:00")
    assert any(c.field == "Play Yards" for c in corrections)


def test_correction_detected_on_player_change():
    drive = _td_drive()
    prev = snapshot_all_drives([drive])

    # Simulate ESPN changing the scoring player
    drive.plays[-1].athletes[1] = Player("99", "Chris Godwin")
    curr = snapshot_all_drives([drive])

    corrections = diff_drives(prev, curr, {"d1": "TB Drive 1"}, "12:03:00")
    player_corrections = [c for c in corrections if c.field == "Players Involved"]
    assert len(player_corrections) >= 1
    assert "TD Scorer" in player_corrections[0].markets_impacted


def test_play_removal_detected():
    drive = _td_drive()
    prev = snapshot_all_drives([drive])

    # Remove a play
    drive.plays.pop(0)
    curr = snapshot_all_drives([drive])

    corrections = diff_drives(prev, curr, {"d1": "TB Drive 1"}, "12:04:00")
    removed = [c for c in corrections if c.field == "Play Removed"]
    assert len(removed) == 1


def test_new_drive_does_not_trigger_correction():
    """A drive that appears for the first time is not a correction."""
    drive1 = _td_drive("d1")
    drive2 = _punt_drive("d2")

    prev = snapshot_all_drives([drive1])
    curr = snapshot_all_drives([drive1, drive2])  # d2 is new

    corrections = diff_drives(prev, curr, {"d1": "TB Drive 1", "d2": "TB Drive 2"}, "12:05:00")
    # d2 should not generate corrections (it's new data, not a change)
    assert all(c.drive_id != "d2" for c in corrections)


def test_merge_corrections_caps_at_max():
    existing = [StatCorrection("t", "d1", "L1", "f", "p", "n") for _ in range(150)]
    new = [StatCorrection("t", "d2", "L2", "f", "p", "n") for _ in range(100)]
    merged = merge_corrections(existing, new, max_history=200)
    assert len(merged) == 200
    # Should keep the most recent (tail)
    assert all(c.drive_id == "d2" for c in merged[100:])


# ------------------------------------------------------------------ #
# Integration: ESPN provider → rules → QC
# ------------------------------------------------------------------ #

def test_full_pipeline_tb_car():
    """End-to-end: ESPN → drives → rules → QC comparator with empty system results."""
    from services.espn_provider import ESPNProvider
    provider = ESPNProvider()
    drives = provider.get_drives("401772912")

    from rules.engine import evaluate_all_drives
    evs = evaluate_all_drives(drives, League.NFL)

    # No system results entered — everything should be Pending or N/A
    dqcs = compare_all_drives(evs, {})

    assert len(dqcs) == len(drives)
    for dqc in dqcs:
        for r in dqc.results:
            assert r.status in (QCStatus.PENDING, QCStatus.NOT_APPLICABLE, QCStatus.MISSING_DATA), \
                f"Unexpected status {r.status} for {dqc.drive_label} / {r.market}"


if __name__ == "__main__":
    passed = failed = 0
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    # Run non-network tests first, network test last
    non_network = [t for t in tests if t.__name__ != "test_full_pipeline_tb_car"]
    network = [t for t in tests if t.__name__ == "test_full_pipeline_tb_car"]
    for test_fn in non_network + network:
        try:
            test_fn()
            print(f"  PASS  {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test_fn.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed out of {passed + failed} tests")
