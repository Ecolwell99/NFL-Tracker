from __future__ import annotations
import requests
from models.game import Game, Team, Score, GameClock, GameStatus, League
from models.drive import Drive, DriveResult, DriveResultGranular, DriveResultExact, DriveResultGrouped, SpecialTeamsScore
from models.play import Play, PlayType, Player
from services.provider_base import FootballDataProvider

# ESPN uses the same API shape for both leagues — only the path segment differs.
_LEAGUE_PATH = {
    League.NFL: "nfl",
    League.CFB: "college-football",
}


def _scoreboard_url(league: League) -> str:
    path = _LEAGUE_PATH.get(league, "nfl")
    return f"https://site.api.espn.com/apis/site/v2/sports/football/{path}/scoreboard"


def _summary_url(league: League, game_id: str) -> str:
    path = _LEAGUE_PATH.get(league, "nfl")
    return f"https://site.api.espn.com/apis/site/v2/sports/football/{path}/summary?event={game_id}"

_ESPN_STATUS_MAP = {
    "1": GameStatus.SCHEDULED,
    "2": GameStatus.IN_PROGRESS,
    "3": GameStatus.FINAL,
    "6": GameStatus.POSTPONED,
}

_ESPN_RESULT_TO_GRANULAR = {
    "TD": None,             # resolved further via play types below
    "FG": DriveResultGranular.FG_MADE,
    "PUNT": DriveResultGranular.PUNT,
    "INT": DriveResultGranular.INTERCEPTION,
    "INT TD": DriveResultGranular.INTERCEPTION,
    "FUMBLE": DriveResultGranular.FUMBLE,
    "FUMBLE TD": DriveResultGranular.FUMBLE,
    "DOWNS": DriveResultGranular.TURNOVER_ON_DOWNS_OR_SAFETY,
    "SAFETY": DriveResultGranular.TURNOVER_ON_DOWNS_OR_SAFETY,
    "MISSED FG": DriveResultGranular.FG_MISSED,
    "BLOCKED FG": DriveResultGranular.FG_MISSED,
    "END OF HALF": DriveResultGranular.END_OF_HALF,
    "END OF GAME": DriveResultGranular.END_OF_HALF,
    "END OF 4TH QUARTER": DriveResultGranular.END_OF_HALF,
    "FUMBLE RETURN TD": DriveResultGranular.FUMBLE,
}


class RateLimitedError(Exception):
    pass


def _fetch_json(url: str) -> dict:
    response = requests.get(url, timeout=10)
    if response.status_code == 429:
        raise RateLimitedError(f"Rate limited by ESPN API (429): {url}")
    response.raise_for_status()
    return response.json()


def _parse_team(raw: dict) -> Team:
    return Team(
        id=str(raw.get("id", "")),
        name=raw.get("name", ""),
        full_name=raw.get("displayName", raw.get("name", "")),
        abbreviation=raw.get("abbreviation", "").upper(),
        color=f"#{raw.get('color', '888888')}",
        alternate_color=f"#{raw.get('alternateColor', 'ffffff')}",
        logo_url=(raw.get("logos") or [{}])[0].get("href", "")
            if raw.get("logos") else raw.get("logo", ""),
    )


def _parse_game_status(competition: dict) -> tuple[GameStatus, GameClock]:
    status_raw = competition.get("status", {})
    type_raw = status_raw.get("type", {})
    state = type_raw.get("state", "")
    type_id = str(type_raw.get("id", "1"))
    description = type_raw.get("description", "")

    if state == "in":
        game_status = GameStatus.IN_PROGRESS
        if "halftime" in description.lower():
            game_status = GameStatus.HALFTIME
    elif state == "post":
        game_status = GameStatus.FINAL
    else:
        game_status = _ESPN_STATUS_MAP.get(type_id, GameStatus.SCHEDULED)

    clock = GameClock(
        period=status_raw.get("period", 1),
        clock=status_raw.get("displayClock", "0:00"),
        is_intermission="halftime" in description.lower(),
        is_final=game_status == GameStatus.FINAL,
    )
    return game_status, clock


def _parse_players_from_play(raw_play: dict) -> list[Player]:
    players = []
    for entry in raw_play.get("athletes", []):
        athlete = entry.get("athlete", {})
        pid = str(athlete.get("id", ""))
        if pid:
            players.append(Player(
                player_id=pid,
                display_name=athlete.get("displayName", ""),
                position=athlete.get("position", {}).get("abbreviation", "")
                    if isinstance(athlete.get("position"), dict) else "",
            ))
    return players


def _parse_play(raw: dict, sequence: int) -> Play:
    type_raw = raw.get("type", {})
    type_id = str(type_raw.get("id", "0"))
    type_text = type_raw.get("text", "")
    description = raw.get("text", "")
    play_type = PlayType.from_espn_id(type_id, description)

    start = raw.get("start", {})
    end = raw.get("end", {})

    # yardsToEndzone: 0 = opponent endzone (score), 100 = own endzone
    start_yte = start.get("yardsToEndzone", 0) if isinstance(start, dict) else 0
    end_yte = end.get("yardsToEndzone", 0) if isinstance(end, dict) else 0

    down = start.get("down", 0) if isinstance(start, dict) else 0
    distance = start.get("distance", 0) if isinstance(start, dict) else 0

    period_raw = raw.get("period", {})
    period = period_raw.get("number", 1) if isinstance(period_raw, dict) else 1

    return Play(
        play_id=str(raw.get("id", sequence)),
        sequence=sequence,
        play_type=play_type,
        yards=raw.get("statYardage", 0) or 0,
        down=down,
        distance=distance,
        yard_line=start_yte,
        end_yard_line=end_yte,
        description=description,
        is_scoring=raw.get("scoringPlay", False),
        is_penalty="penalty" in description.lower() or play_type == PlayType.PENALTY,
        period=period,
        clock=raw.get("clock", {}).get("displayValue", "") if isinstance(raw.get("clock"), dict) else "",
        athletes=_parse_players_from_play(raw),
    )


def _granular_from_espn(espn_result: str, plays: list[Play]) -> DriveResultGranular:
    result_upper = espn_result.strip().upper()

    # TD needs further resolution from play types
    if result_upper == "TD":
        for play in reversed(plays):
            if play.play_type == PlayType.PASSING_TD:
                return DriveResultGranular.PASSING_TD
            if play.play_type == PlayType.RUSHING_TD:
                return DriveResultGranular.RUSHING_TD
        return DriveResultGranular.RUSHING_TD  # fallback

    # Check all mappings including partial matches
    if result_upper in _ESPN_RESULT_TO_GRANULAR:
        return _ESPN_RESULT_TO_GRANULAR[result_upper]

    # Fuzzy fallback
    if "TOUCHDOWN" in result_upper or result_upper.startswith("TD"):
        for play in reversed(plays):
            if play.play_type == PlayType.PASSING_TD:
                return DriveResultGranular.PASSING_TD
            if play.play_type == PlayType.RUSHING_TD:
                return DriveResultGranular.RUSHING_TD
    if "PUNT" in result_upper:
        return DriveResultGranular.PUNT
    if "FIELD GOAL" in result_upper and ("MISS" in result_upper or "BLOCK" in result_upper):
        return DriveResultGranular.FG_MISSED
    if "FIELD GOAL" in result_upper:
        return DriveResultGranular.FG_MADE
    if "INTERCEPTION" in result_upper or result_upper.startswith("INT"):
        return DriveResultGranular.INTERCEPTION
    if "FUMBLE" in result_upper:
        return DriveResultGranular.FUMBLE
    if "DOWNS" in result_upper or "SAFETY" in result_upper:
        return DriveResultGranular.TURNOVER_ON_DOWNS_OR_SAFETY
    if "HALF" in result_upper or "GAME" in result_upper or "QUARTER" in result_upper:
        return DriveResultGranular.END_OF_HALF

    return DriveResultGranular.UNKNOWN


def _build_drive_result(granular: DriveResultGranular) -> DriveResult:
    _TO_EXACT = {
        DriveResultGranular.RUSHING_TD: DriveResultExact.TD,
        DriveResultGranular.PASSING_TD: DriveResultExact.TD,
        DriveResultGranular.FG_MADE: DriveResultExact.FG,
        DriveResultGranular.FG_MISSED: DriveResultExact.FG,
        DriveResultGranular.PUNT: DriveResultExact.PUNT,
        DriveResultGranular.TURNOVER_ON_DOWNS_OR_SAFETY: DriveResultExact.TURNOVER,
        DriveResultGranular.INTERCEPTION: DriveResultExact.TURNOVER,
        DriveResultGranular.FUMBLE: DriveResultExact.TURNOVER,
        DriveResultGranular.END_OF_HALF: DriveResultExact.VOID,
        DriveResultGranular.UNKNOWN: DriveResultExact.UNKNOWN,
    }
    _TO_GROUPED = {
        DriveResultGranular.RUSHING_TD: DriveResultGrouped.OFFENSIVE_SCORE,
        DriveResultGranular.PASSING_TD: DriveResultGrouped.OFFENSIVE_SCORE,
        DriveResultGranular.FG_MADE: DriveResultGrouped.OFFENSIVE_SCORE,
        DriveResultGranular.FG_MISSED: DriveResultGrouped.NO_OFFENSIVE_SCORE,
        DriveResultGranular.PUNT: DriveResultGrouped.NO_OFFENSIVE_SCORE,
        DriveResultGranular.TURNOVER_ON_DOWNS_OR_SAFETY: DriveResultGrouped.NO_OFFENSIVE_SCORE,
        DriveResultGranular.INTERCEPTION: DriveResultGrouped.NO_OFFENSIVE_SCORE,
        DriveResultGranular.FUMBLE: DriveResultGrouped.NO_OFFENSIVE_SCORE,
        DriveResultGranular.END_OF_HALF: DriveResultGrouped.VOID,
        DriveResultGranular.UNKNOWN: DriveResultGrouped.UNKNOWN,
    }
    return DriveResult(
        granular=granular,
        exact=_TO_EXACT.get(granular, DriveResultExact.UNKNOWN),
        grouped=_TO_GROUPED.get(granular, DriveResultGrouped.UNKNOWN),
    )


def _parse_drive(raw: dict, sequence: int, team_map: dict[str, Team], is_current: bool = False) -> Drive:
    team_raw = raw.get("team", {})
    team_id = str(team_raw.get("id", ""))
    team = team_map.get(team_id) or _parse_team(team_raw)

    raw_plays = raw.get("plays", [])
    plays = [_parse_play(p, i) for i, p in enumerate(raw_plays)]

    espn_result = raw.get("result", "").strip().upper()
    granular = _granular_from_espn(espn_result, plays)
    result = _build_drive_result(granular)

    start_raw = raw.get("start", {})
    end_raw = raw.get("end", {})

    # Scores at the end of the drive
    score_home = 0
    score_away = 0
    if isinstance(end_raw, dict):
        score_home = int(end_raw.get("homeScore", 0) or 0)
        score_away = int(end_raw.get("awayScore", 0) or 0)

    # T.O.P. — ESPN returns either a plain string or {"displayValue": "4:30"}
    top_raw = raw.get("timeElapsed", "")
    if isinstance(top_raw, dict):
        top_raw = top_raw.get("displayValue", "")

    # Use ESPN's pre-formatted text (e.g. "CAR 35") for display; fall back to yardLine
    start_text = start_raw.get("text", "") if isinstance(start_raw, dict) else ""
    start_yardline_raw = start_raw.get("yardLine", 0) if isinstance(start_raw, dict) else 0

    return Drive(
        drive_id=str(raw.get("id", f"drive_{sequence}")),
        game_id="",
        sequence=sequence,
        team=team,
        team_drive_number=0,
        plays=plays,
        start_yardline=start_raw.get("yardsToEndzone", 0) if isinstance(start_raw, dict) else 0,
        end_yardline=end_raw.get("yardsToEndzone", 0) if isinstance(end_raw, dict) else 0,
        start_yardline_raw=start_yardline_raw,
        start_text=start_text,
        yards_gained=raw.get("yards", 0) or 0,
        time_of_possession=top_raw,
        play_count=raw.get("offensivePlays", len(plays)),
        description=raw.get("description", ""),
        score_home=score_home,
        score_away=score_away,
        is_current=is_current,
        espn_result=espn_result,
        result=result,
    )


def _assign_team_drive_numbers(drives: list[Drive]) -> list[Drive]:
    """Compute per-team sequential drive numbers (mirrors COUNTIF formula from workbook)."""
    counts: dict[str, int] = {}
    for drive in drives:
        tid = drive.team.id
        counts[tid] = counts.get(tid, 0) + 1
        drive.team_drive_number = counts[tid]
    return drives


class ESPNProvider(FootballDataProvider):

    def get_games(self, league: League = League.NFL) -> list[Game]:
        data = _fetch_json(_scoreboard_url(league))
        games = []
        for event in data.get("events", []):
            game = self._parse_event(event, league)
            if game:
                games.append(game)
        return games

    def get_game(self, game_id: str, league: League = League.NFL) -> Game:
        data = _fetch_json(_summary_url(league, game_id))
        return self._parse_summary_game(game_id, data, league)

    def get_drives(self, game_id: str, league: League = League.NFL) -> list[Drive]:
        data = _fetch_json(_summary_url(league, game_id))
        drives, _ = self._split_drives(game_id, data)
        return drives

    def get_special_teams_scores(self, game_id: str, league: League = League.NFL) -> list[SpecialTeamsScore]:
        data = _fetch_json(_summary_url(league, game_id))
        _, st_scores = self._split_drives(game_id, data)
        return st_scores

    def get_plays(self, game_id: str, league: League = League.NFL) -> list[Play]:
        drives = self.get_drives(game_id, league)
        plays = []
        for drive in drives:
            plays.extend(drive.plays)
        return plays

    def get_boxscore(self, game_id: str, league: League = League.NFL) -> dict:
        data = _fetch_json(_summary_url(league, game_id))
        return data.get("boxscore", {})

    # ------------------------------------------------------------------ #
    # Internal parsers
    # ------------------------------------------------------------------ #

    def _parse_event(self, event: dict, league: League = League.NFL) -> Game | None:
        competitions = event.get("competitions", [])
        if not competitions:
            return None
        comp = competitions[0]
        competitors = comp.get("competitors", [])
        if len(competitors) < 2:
            return None

        home_raw = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away_raw = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home_team = _parse_team(home_raw.get("team", {}))
        away_team = _parse_team(away_raw.get("team", {}))

        home_score = int(home_raw.get("score", 0) or 0)
        away_score = int(away_raw.get("score", 0) or 0)

        status, clock = _parse_game_status(comp)

        season     = event.get("season") or {}
        season_type_raw = season.get("type") if isinstance(season, dict) else None
        season_type_str = (
            season_type_raw.get("abbreviation", "")
            if isinstance(season_type_raw, dict)
            else ""
        )
        week_raw = event.get("week") or {}
        week_num = week_raw.get("number") if isinstance(week_raw, dict) else None

        return Game(
            game_id=str(event.get("id", "")),
            league=league,
            home_team=home_team,
            away_team=away_team,
            date=event.get("date", ""),
            status=status,
            score=Score(home=home_score, away=away_score),
            clock=clock,
            venue=comp.get("venue", {}).get("fullName", "") if isinstance(comp.get("venue"), dict) else "",
            season_type=season_type_str,
            week=week_num,
        )

    def _parse_summary_game(self, game_id: str, data: dict, league: League = League.NFL) -> Game:
        # summary endpoint wraps game info differently
        header = data.get("header", {})
        competitions = header.get("competitions", [])
        if competitions:
            header_season = header.get("season") or {}
            fake_event = {
                "id": game_id,
                "competitions": competitions,
                "date": header_season.get("year", "") if isinstance(header_season, dict) else "",
                "season": header_season if isinstance(header_season, dict) else {},
                "week": header.get("week") or {},
            }
            game = self._parse_event(fake_event, league)
            if game:
                return game

        # Fallback: build from boxscore teams
        boxscore = data.get("boxscore", {})
        teams = boxscore.get("teams", [])
        home_raw = next((t for t in teams if t.get("homeAway") == "home"), teams[0] if teams else {})
        away_raw = next((t for t in teams if t.get("homeAway") == "away"), teams[1] if len(teams) > 1 else {})
        return Game(
            game_id=game_id,
            league=league,
            home_team=_parse_team(home_raw.get("team", {})),
            away_team=_parse_team(away_raw.get("team", {})),
            date="",
            status=GameStatus.FINAL,
        )

    def _split_drives(
        self, game_id: str, data: dict
    ) -> tuple[list[Drive], list[SpecialTeamsScore]]:
        drives_raw = data.get("drives", {})
        if not drives_raw:
            return [], []

        # Build team map from boxscore for fast lookup
        team_map: dict[str, Team] = {}
        for t in data.get("boxscore", {}).get("teams", []):
            team = _parse_team(t.get("team", {}))
            team_map[team.id] = team

        previous = drives_raw.get("previous", []) or []
        current = drives_raw.get("current")

        all_raw = list(previous)
        current_id = None
        if isinstance(current, dict) and current.get("id"):
            all_raw.append(current)
            current_id = str(current.get("id"))

        # ESPN logs special-teams scores (kickoff/punt return TDs) as standalone
        # "drives" with zero offensive snaps. Mirror the Excel workbook and drop
        # any drive with no offensive plays — but keep the live current drive,
        # which can briefly show 0 plays right after it starts.
        def _has_offensive_snaps(raw: dict) -> bool:
            if str(raw.get("id")) == current_id:
                return True
            return int(raw.get("offensivePlays", 0) or 0) > 0

        # Walk the raw list in game order, keeping offensive drives and turning
        # dropped zero-snap *scoring* drives into inline markers. The marker's
        # sort key sits just before the next kept drive's sequence so it renders
        # in the right chronological spot.
        drives: list[Drive] = []
        st_scores: list[SpecialTeamsScore] = []
        seq = 0
        for raw in all_raw:
            if _has_offensive_snaps(raw):
                seq += 1
                drive = _parse_drive(
                    raw, seq, team_map,
                    is_current=(str(raw.get("id")) == current_id),
                )
                drive.game_id = game_id
                drives.append(drive)
            elif str(raw.get("result", "")).strip().upper() in ("TD", "SAFETY"):
                team_raw = raw.get("team", {})
                team = team_map.get(str(team_raw.get("id", ""))) or _parse_team(team_raw)
                end_raw = raw.get("end", {})
                st_scores.append(SpecialTeamsScore(
                    team=team,
                    sequence=seq + 0.5,  # between the last kept drive and the next
                    espn_result=str(raw.get("result", "")).strip().upper(),
                    score_home=int(end_raw.get("homeScore", 0) or 0) if isinstance(end_raw, dict) else 0,
                    score_away=int(end_raw.get("awayScore", 0) or 0) if isinstance(end_raw, dict) else 0,
                ))

        return _assign_team_drive_numbers(drives), st_scores
