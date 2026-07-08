"""
Unit tests for the rules engine.
All tests use synthetic Drive/Play objects — no network calls, no Streamlit.
Run from nfl_qc_tool/: python -m pytest tests/test_rules.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.game import Team, League
from models.drive import Drive, DriveResult, DriveResultGranular, DriveResultExact, DriveResultGrouped
from models.play import Play, PlayType, Player
from rules.drive_result import drive_result_exact, drive_result_grouped, compute_drive_result
from rules.yardlines import crossed_midfield, crossed_opp_35, crossed_opp_20, validate_yardline_chain
from rules.plays import (
    had_sack, had_20_plus_passing_play, had_10_plus_rushing_play,
    had_20_plus_play, punt_fair_catch, converted_fourth_down,
)
from rules.scoring import td_scorer, td_scorer_display, pass_catchers_display
from rules.validators import DriveMarketValues, validate_drive
from rules.engine import evaluate_drive


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

_TEAM = Team(id="1", name="Patriots", full_name="New England Patriots",
             abbreviation="NE", color="#002244")


def _drive(plays=None, espn_result="", granular=None):
    result = DriveResult(
        granular=granular or DriveResultGranular.UNKNOWN,
        exact=drive_result_exact(granular or DriveResultGranular.UNKNOWN),
        grouped=drive_result_grouped(granular or DriveResultGranular.UNKNOWN),
    ) if granular else None
    return Drive(
        drive_id="d1", game_id="g1", sequence=1,
        team=_TEAM, team_drive_number=1,
        plays=plays or [],
        espn_result=espn_result,
        result=result,
    )


def _play(play_type, yards=0, down=1, yard_line=65, end_yard_line=None,
          is_scoring=False, athletes=None, description=""):
    return Play(
        play_id="p1", sequence=1,
        play_type=play_type,
        yards=yards,
        down=down,
        distance=10,
        yard_line=yard_line,
        end_yard_line=end_yard_line if end_yard_line is not None else max(0, yard_line - yards),
        description=description,
        is_scoring=is_scoring,
        athletes=athletes or [],
    )


def _player(pid, name):
    return Player(player_id=pid, display_name=name)


# ------------------------------------------------------------------ #
# Drive Result hierarchy
# ------------------------------------------------------------------ #

def test_drive_result_exact_td():
    assert drive_result_exact(DriveResultGranular.RUSHING_TD) == DriveResultExact.TD
    assert drive_result_exact(DriveResultGranular.PASSING_TD) == DriveResultExact.TD


def test_drive_result_exact_fg():
    assert drive_result_exact(DriveResultGranular.FG_MADE) == DriveResultExact.FG
    assert drive_result_exact(DriveResultGranular.FG_MISSED) == DriveResultExact.FG


def test_drive_result_exact_turnover():
    assert drive_result_exact(DriveResultGranular.INTERCEPTION) == DriveResultExact.TURNOVER
    assert drive_result_exact(DriveResultGranular.FUMBLE) == DriveResultExact.TURNOVER
    assert drive_result_exact(DriveResultGranular.TURNOVER_ON_DOWNS_OR_SAFETY) == DriveResultExact.TURNOVER


def test_drive_result_exact_void():
    assert drive_result_exact(DriveResultGranular.END_OF_HALF) == DriveResultExact.VOID


def test_drive_result_grouped_offensive_score():
    assert drive_result_grouped(DriveResultGranular.RUSHING_TD) == DriveResultGrouped.OFFENSIVE_SCORE
    assert drive_result_grouped(DriveResultGranular.PASSING_TD) == DriveResultGrouped.OFFENSIVE_SCORE
    assert drive_result_grouped(DriveResultGranular.FG_MADE) == DriveResultGrouped.OFFENSIVE_SCORE


def test_drive_result_grouped_no_score():
    assert drive_result_grouped(DriveResultGranular.FG_MISSED) == DriveResultGrouped.NO_OFFENSIVE_SCORE
    assert drive_result_grouped(DriveResultGranular.PUNT) == DriveResultGrouped.NO_OFFENSIVE_SCORE
    assert drive_result_grouped(DriveResultGranular.INTERCEPTION) == DriveResultGrouped.NO_OFFENSIVE_SCORE


def test_drive_result_grouped_void():
    assert drive_result_grouped(DriveResultGranular.END_OF_HALF) == DriveResultGrouped.VOID


# ------------------------------------------------------------------ #
# Yard-line crossing
# ------------------------------------------------------------------ #

def test_td_drive_crosses_all_lines():
    drive = _drive(
        plays=[_play(PlayType.RUSHING_TD, yards=7, yard_line=7, end_yard_line=0, is_scoring=True)],
        granular=DriveResultGranular.RUSHING_TD,
    )
    assert crossed_midfield(drive) is True
    assert crossed_opp_35(drive) is True
    assert crossed_opp_20(drive) is True


def test_drive_that_reaches_opp_15_crosses_all():
    plays = [
        _play(PlayType.RUSH, yards=10, yard_line=65, end_yard_line=55),
        _play(PlayType.PASS_COMPLETE, yards=20, yard_line=55, end_yard_line=35),
        _play(PlayType.RUSH, yards=5, yard_line=35, end_yard_line=30),
        _play(PlayType.PASS_COMPLETE, yards=15, yard_line=30, end_yard_line=15),
        _play(PlayType.FIELD_GOAL_GOOD, yards=0, yard_line=15, end_yard_line=15),
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.FG_MADE)
    assert crossed_midfield(drive) is True
    assert crossed_opp_35(drive) is True
    assert crossed_opp_20(drive) is True


def test_drive_only_crosses_midfield():
    plays = [
        _play(PlayType.RUSH, yards=10, yard_line=65, end_yard_line=55),
        _play(PlayType.PASS_COMPLETE, yards=8, yard_line=55, end_yard_line=47),
        _play(PlayType.PUNT, yards=0, yard_line=47, end_yard_line=47),
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.PUNT)
    assert crossed_midfield(drive) is True
    assert crossed_opp_35(drive) is False
    assert crossed_opp_20(drive) is False


def test_drive_never_crosses_midfield():
    plays = [
        _play(PlayType.RUSH, yards=3, yard_line=75, end_yard_line=72),
        _play(PlayType.PASS_INCOMPLETE, yards=0, yard_line=72, end_yard_line=72),
        _play(PlayType.PUNT, yards=0, yard_line=72, end_yard_line=72),
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.PUNT)
    assert crossed_midfield(drive) is False
    assert crossed_opp_35(drive) is False
    assert crossed_opp_20(drive) is False


def test_yardline_chain_valid():
    assert validate_yardline_chain(True, True, True) == []
    assert validate_yardline_chain(True, True, False) == []
    assert validate_yardline_chain(False, False, False) == []


def test_yardline_chain_opp20_without_opp35():
    warnings = validate_yardline_chain(True, False, True)
    assert any("Opp35" in w for w in warnings)


def test_yardline_chain_cross50_no_with_opp35():
    warnings = validate_yardline_chain(False, True, False)
    assert any("Opp35" in w for w in warnings)


# ------------------------------------------------------------------ #
# Play markets
# ------------------------------------------------------------------ #

def test_had_sack_true():
    drive = _drive(plays=[
        _play(PlayType.RUSH, yards=5),
        _play(PlayType.SACK, yards=-8),
    ])
    assert had_sack(drive) is True


def test_had_sack_false():
    drive = _drive(plays=[_play(PlayType.RUSH, yards=5)])
    assert had_sack(drive) is False


def test_20_plus_passing_play_exact_boundary():
    # 19 yards = No
    drive = _drive(plays=[_play(PlayType.PASS_COMPLETE, yards=19)])
    assert had_20_plus_passing_play(drive) is False
    # 20 yards = Yes
    drive = _drive(plays=[_play(PlayType.PASS_COMPLETE, yards=20)])
    assert had_20_plus_passing_play(drive) is True


def test_20_plus_passing_play_includes_td():
    drive = _drive(plays=[_play(PlayType.PASSING_TD, yards=25, is_scoring=True)])
    assert had_20_plus_passing_play(drive) is True


def test_20_plus_passing_play_excludes_rush():
    drive = _drive(plays=[_play(PlayType.RUSH, yards=25)])
    assert had_20_plus_passing_play(drive) is False


def test_10_plus_rushing_play_boundary():
    drive = _drive(plays=[_play(PlayType.RUSH, yards=9)])
    assert had_10_plus_rushing_play(drive) is False
    drive = _drive(plays=[_play(PlayType.RUSH, yards=10)])
    assert had_10_plus_rushing_play(drive) is True


def test_20_plus_play_any_type():
    # Rush over 20 = yes
    drive = _drive(plays=[_play(PlayType.RUSH, yards=21)])
    assert had_20_plus_play(drive) is True
    # Pass over 20 = yes
    drive = _drive(plays=[_play(PlayType.PASS_COMPLETE, yards=22)])
    assert had_20_plus_play(drive) is True
    # Sack even with 20 negative = no
    drive = _drive(plays=[_play(PlayType.SACK, yards=-20)])
    assert had_20_plus_play(drive) is False


def test_punt_fair_catch_na_on_non_punt():
    drive = _drive(granular=DriveResultGranular.FG_MADE)
    assert punt_fair_catch(drive) is None


def test_punt_fair_catch_detected():
    plays = [
        _play(PlayType.RUSH, yards=3),
        _play(PlayType.PUNT, yards=0, description="J.Hekker punts 48 yards. Fair catch by D.Adams."),
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.PUNT)
    assert punt_fair_catch(drive) is True


def test_punt_no_fair_catch():
    plays = [
        _play(PlayType.PUNT, yards=0,
              description="J.Hekker punts 42 yards. K.Johnson returns 8 yards."),
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.PUNT)
    assert punt_fair_catch(drive) is False


def test_fourth_down_conversion():
    plays = [
        _play(PlayType.RUSH, yards=2, down=1),
        _play(PlayType.PASS_INCOMPLETE, yards=0, down=2),
        _play(PlayType.RUSH, yards=1, down=3),
        _play(PlayType.PASS_COMPLETE, yards=12, down=4),  # conversion
        _play(PlayType.RUSH, yards=5, down=1),
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.PUNT)
    assert converted_fourth_down(drive) is True


def test_no_fourth_down_conversion():
    plays = [
        _play(PlayType.RUSH, yards=3, down=1),
        _play(PlayType.RUSH, yards=4, down=2),
        _play(PlayType.PASS_COMPLETE, yards=5, down=3),
        _play(PlayType.PUNT, yards=0, down=4),  # kicked — not a conversion attempt
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.PUNT)
    assert converted_fourth_down(drive) is False


# ------------------------------------------------------------------ #
# Scoring
# ------------------------------------------------------------------ #

def test_td_scorer_rushing():
    rusher = _player("10", "Derrick Henry")
    plays = [_play(PlayType.RUSHING_TD, yards=7, is_scoring=True, athletes=[rusher])]
    drive = _drive(plays=plays, granular=DriveResultGranular.RUSHING_TD)
    scorer = td_scorer(drive)
    assert scorer is not None
    assert scorer.display_name == "Derrick Henry"


def test_td_scorer_passing():
    qb = _player("1", "Baker Mayfield")
    receiver = _player("2", "Mike Evans")
    plays = [_play(PlayType.PASSING_TD, yards=15, is_scoring=True, athletes=[qb, receiver])]
    drive = _drive(plays=plays, granular=DriveResultGranular.PASSING_TD)
    scorer = td_scorer(drive)
    assert scorer is not None
    assert scorer.display_name == "Mike Evans"


def test_td_scorer_display_passing():
    qb = _player("1", "Baker Mayfield")
    receiver = _player("2", "Mike Evans")
    plays = [_play(PlayType.PASSING_TD, yards=15, is_scoring=True, athletes=[qb, receiver])]
    drive = _drive(plays=plays, granular=DriveResultGranular.PASSING_TD)
    display = td_scorer_display(drive)
    assert "Mike Evans" in display
    assert "Mayfield" in display


def test_td_scorer_na_on_non_td():
    drive = _drive(granular=DriveResultGranular.FG_MADE)
    assert td_scorer_display(drive) == "N/A"


def test_pass_catchers_deduped():
    qb = _player("1", "Patrick Mahomes")
    rec1 = _player("2", "Travis Kelce")
    rec2 = _player("3", "Rashee Rice")
    plays = [
        _play(PlayType.PASS_COMPLETE, yards=8, athletes=[qb, rec1]),
        _play(PlayType.PASS_COMPLETE, yards=12, athletes=[qb, rec1]),  # duplicate
        _play(PlayType.PASS_COMPLETE, yards=6, athletes=[qb, rec2]),
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.FG_MADE)
    catchers = pass_catchers_display(drive)
    assert "T. Kelce" in catchers
    assert "R. Rice" in catchers
    # Kelce should appear only once
    assert catchers.count("Kelce") == 1


# ------------------------------------------------------------------ #
# Validators
# ------------------------------------------------------------------ #

def test_validator_clean_td_drive():
    vals = DriveMarketValues(
        granular=DriveResultGranular.PASSING_TD,
        exact=DriveResultExact.TD,
        grouped=DriveResultGrouped.OFFENSIVE_SCORE,
        cross_50=True, opp_35=True, opp_20=True,
        sack=False, fair_catch=None,
        td_scorer="Mike Evans (pass from Mayfield)",
        passing_20_plus=True, rushing_10_plus=False,
        play_20_plus=True, fourth_down_conversion=False,
    )
    assert validate_drive(vals) == []


def test_validator_td_missing_opp20():
    vals = DriveMarketValues(
        granular=DriveResultGranular.RUSHING_TD,
        exact=DriveResultExact.TD,
        grouped=DriveResultGrouped.OFFENSIVE_SCORE,
        cross_50=True, opp_35=True, opp_20=False,  # wrong
        sack=False, fair_catch=None,
        td_scorer="Derrick Henry",
        passing_20_plus=None, rushing_10_plus=None,
        play_20_plus=None, fourth_down_conversion=None,
    )
    warnings = validate_drive(vals)
    assert any("Opp20" in w for w in warnings)


def test_validator_non_punt_with_fair_catch():
    vals = DriveMarketValues(
        granular=DriveResultGranular.FG_MADE,
        exact=DriveResultExact.FG,
        grouped=DriveResultGrouped.OFFENSIVE_SCORE,
        cross_50=True, opp_35=True, opp_20=True,
        sack=False, fair_catch=True,  # wrong — should be N/A
        td_scorer="N/A",
        passing_20_plus=False, rushing_10_plus=False,
        play_20_plus=False, fourth_down_conversion=False,
    )
    warnings = validate_drive(vals)
    assert any("Fair Catch" in w for w in warnings)


def test_validator_td_scorer_missing():
    vals = DriveMarketValues(
        granular=DriveResultGranular.PASSING_TD,
        exact=DriveResultExact.TD,
        grouped=DriveResultGrouped.OFFENSIVE_SCORE,
        cross_50=True, opp_35=True, opp_20=True,
        sack=False, fair_catch=None,
        td_scorer="",  # missing
        passing_20_plus=False, rushing_10_plus=False,
        play_20_plus=False, fourth_down_conversion=False,
    )
    warnings = validate_drive(vals)
    assert any("TD Scorer" in w and "missing" in w for w in warnings)


def test_validator_20plus_pass_implies_20plus_play():
    vals = DriveMarketValues(
        granular=DriveResultGranular.PUNT,
        exact=DriveResultExact.PUNT,
        grouped=DriveResultGrouped.NO_OFFENSIVE_SCORE,
        cross_50=True, opp_35=False, opp_20=False,
        sack=False, fair_catch=False,
        td_scorer="N/A",
        passing_20_plus=True, rushing_10_plus=False,
        play_20_plus=False,  # wrong — should be True if passing_20_plus is True
        fourth_down_conversion=False,
    )
    warnings = validate_drive(vals)
    assert any("20+ Yard Play" in w for w in warnings)


# ------------------------------------------------------------------ #
# Full engine integration
# ------------------------------------------------------------------ #

def test_evaluate_drive_td():
    qb = _player("1", "Baker Mayfield")
    receiver = _player("2", "Mike Evans")
    plays = [
        _play(PlayType.RUSH, yards=8, down=1, yard_line=65, end_yard_line=57),
        _play(PlayType.PASS_COMPLETE, yards=22, down=2, yard_line=57, end_yard_line=35),
        _play(PlayType.RUSH, yards=15, down=1, yard_line=35, end_yard_line=20),
        _play(PlayType.PASS_COMPLETE, yards=12, down=1, yard_line=20, end_yard_line=8),
        _play(PlayType.PASSING_TD, yards=8, down=1, yard_line=8, end_yard_line=0,
              is_scoring=True, athletes=[qb, receiver]),
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.PASSING_TD)

    result = evaluate_drive(drive, League.NFL)

    assert result.result_exact == "TD"
    assert result.result_grouped == "Offensive Score"
    assert result.cross_50 is True
    assert result.opp_35 is True
    assert result.opp_20 is True
    assert result.passing_20_plus is True   # 22-yard pass
    assert "Mike Evans" in result.td_scorer
    assert result.warnings == []


def test_evaluate_drive_punt_no_crossing():
    plays = [
        _play(PlayType.RUSH, yards=3, down=1, yard_line=80, end_yard_line=77),
        _play(PlayType.PASS_INCOMPLETE, yards=0, down=2, yard_line=77, end_yard_line=77),
        _play(PlayType.RUSH, yards=2, down=3, yard_line=77, end_yard_line=75),
        _play(PlayType.PUNT, yards=0, down=4, yard_line=75, end_yard_line=75,
              description="S.Martin punts 44 yards. J.Smith fair catch at the 31."),
    ]
    drive = _drive(plays=plays, granular=DriveResultGranular.PUNT)

    result = evaluate_drive(drive, League.NFL)

    assert result.result_exact == "Punt"
    assert result.cross_50 is False
    assert result.opp_35 is False
    assert result.opp_20 is False
    assert result.fair_catch is True
    assert result.td_scorer == "N/A"
    assert result.warnings == []


if __name__ == "__main__":
    import unittest
    # Simple runner without pytest
    passed = failed = 0
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS  {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test_fn.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed out of {passed + failed} tests")
