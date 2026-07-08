"""
Smoke tests for the ESPN provider using the TB@CAR game from the workbook.
Run from the nfl_qc_tool directory:  python -m pytest tests/ -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.espn_provider import ESPNProvider
from models.drive import DriveResultGranular, DriveResultExact, DriveResultGrouped
from models.play import PlayType

TB_CAR_GAME_ID = "401772912"


def get_provider():
    return ESPNProvider()


def test_get_game_returns_correct_teams():
    p = get_provider()
    game = p.get_game(TB_CAR_GAME_ID)
    abbrevs = {game.home_team.abbreviation, game.away_team.abbreviation}
    assert "TB" in abbrevs or "CAR" in abbrevs, f"Expected TB or CAR, got {abbrevs}"


def test_get_drives_returns_drives():
    p = get_provider()
    drives = p.get_drives(TB_CAR_GAME_ID)
    assert len(drives) >= 10, f"Expected at least 10 drives, got {len(drives)}"


def test_drive_team_numbers_are_sequential():
    p = get_provider()
    drives = p.get_drives(TB_CAR_GAME_ID)
    from collections import defaultdict
    counts = defaultdict(int)
    for drive in drives:
        counts[drive.team.id] += 1
        assert drive.team_drive_number == counts[drive.team.id], (
            f"Drive {drive.drive_id}: expected team_drive_number {counts[drive.team.id]}, "
            f"got {drive.team_drive_number}"
        )


def test_drive_results_are_resolved():
    p = get_provider()
    drives = p.get_drives(TB_CAR_GAME_ID)
    for drive in drives:
        assert drive.result is not None, f"Drive {drive.drive_id} has no result"
        assert drive.result.granular != DriveResultGranular.UNKNOWN, (
            f"Drive {drive.drive_id} has UNKNOWN granular result (ESPN: '{drive.espn_result}')"
        )


def test_td_drives_have_correct_result_hierarchy():
    p = get_provider()
    drives = p.get_drives(TB_CAR_GAME_ID)
    td_drives = [d for d in drives if d.result and d.result.exact == DriveResultExact.TD]
    assert len(td_drives) > 0, "Expected at least one TD drive"
    for d in td_drives:
        assert d.result.grouped == DriveResultGrouped.OFFENSIVE_SCORE
        assert d.result.granular in (
            DriveResultGranular.RUSHING_TD,
            DriveResultGranular.PASSING_TD,
        )


def test_end_of_half_drives_are_void():
    p = get_provider()
    drives = p.get_drives(TB_CAR_GAME_ID)
    void_drives = [d for d in drives if d.result and d.result.exact == DriveResultExact.VOID]
    assert len(void_drives) > 0, "Expected at least one End of Half void drive"
    for d in void_drives:
        assert d.result.grouped == DriveResultGrouped.VOID


def test_plays_have_types():
    p = get_provider()
    drives = p.get_drives(TB_CAR_GAME_ID)
    all_plays = [play for d in drives for play in d.plays]
    assert len(all_plays) > 50, f"Expected >50 plays, got {len(all_plays)}"
    unknown = [p for p in all_plays if p.play_type == PlayType.UNKNOWN]
    # Allow some unknowns but not a majority
    assert len(unknown) < len(all_plays) * 0.1, (
        f"Too many UNKNOWN play types: {len(unknown)}/{len(all_plays)}"
    )


def test_td_plays_have_athletes():
    p = get_provider()
    drives = p.get_drives(TB_CAR_GAME_ID)
    td_plays = [
        play for d in drives for play in d.plays
        if play.play_type in (PlayType.PASSING_TD, PlayType.RUSHING_TD)
    ]
    assert len(td_plays) > 0, "Expected at least one TD play"
    for play in td_plays:
        assert len(play.athletes) > 0, (
            f"TD play {play.play_id} has no athletes: {play.description[:80]}"
        )


if __name__ == "__main__":
    # Quick manual run
    print("Testing ESPN provider with TB@CAR game...")
    p = ESPNProvider()
    game = p.get_game(TB_CAR_GAME_ID)
    print(f"Game: {game.label} | Status: {game.status}")
    drives = p.get_drives(TB_CAR_GAME_ID)
    print(f"Drives: {len(drives)}")
    for d in drives:
        print(f"  {d.label:40s} | ESPN: {d.espn_result:20s} | "
              f"Granular: {d.result.granular.value if d.result else 'None':25s} | "
              f"Exact: {d.result.exact.value if d.result else 'None':10s}")
    print("Done.")
