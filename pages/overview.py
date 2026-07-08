from __future__ import annotations
import streamlit as st
from models.game import Game, GameStatus
from models.drive import Drive
from rules.engine import EvaluatedDrive
from utils.time import period_label
from utils.colors import resolve_team_colors, pill_text_color
from components.warning_box import warning_box


def render(game: Game, drives: list[Drive], evaluated: list[EvaluatedDrive]) -> None:
    _render_scoreboard(game)
    st.divider()
    _render_drive_summary(drives, evaluated, game)


def _render_scoreboard(game: Game) -> None:
    home = game.home_team
    away = game.away_team
    color_map = resolve_team_colors(home.abbreviation, away.abbreviation)
    home_color = color_map.get(home.abbreviation, "#888888")
    away_color = color_map.get(away.abbreviation, "#888888")

    clock = game.clock
    period_str = period_label(clock.period)
    if clock.is_final:
        period_str = "FINAL"
    elif clock.is_intermission:
        period_str = f"{period_str} — INTERMISSION"

    st.markdown(
        f"""
        <div style="display:flex; justify-content:center; align-items:center;
                    gap:40px; padding:24px 0 16px 0;">
            <div style="text-align:center;">
                <div style="background:{away_color}; color:{pill_text_color(away_color)};
                            padding:6px 20px; border-radius:8px; font-weight:800;
                            font-size:28px; letter-spacing:0.05em;">{away.abbreviation}</div>
                <div style="font-size:13px; opacity:0.6; margin-top:4px;">Away</div>
                <div style="font-size:52px; font-weight:900; line-height:1.1;">
                    {game.score.away}
                </div>
            </div>
            <div style="text-align:center; opacity:0.5; font-size:22px; font-weight:700;">
                @
                <div style="font-size:15px; margin-top:8px; font-weight:600;">
                    {period_str}
                </div>
                <div style="font-size:13px; margin-top:2px;">{clock.clock}</div>
            </div>
            <div style="text-align:center;">
                <div style="background:{home_color}; color:{pill_text_color(home_color)};
                            padding:6px 20px; border-radius:8px; font-weight:800;
                            font-size:28px; letter-spacing:0.05em;">{home.abbreviation}</div>
                <div style="font-size:13px; opacity:0.6; margin-top:4px;">Home</div>
                <div style="font-size:52px; font-weight:900; line-height:1.1;">
                    {game.score.home}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if game.venue:
        st.markdown(
            f'<div style="text-align:center; font-size:12px; opacity:0.4; '
            f'margin-bottom:8px;">{game.venue}</div>',
            unsafe_allow_html=True,
        )


def _render_drive_summary(
    drives: list[Drive],
    evaluated: list[EvaluatedDrive],
    game: Game,
) -> None:
    if not drives:
        st.info("No drive data yet.")
        return

    col1, col2, col3, col4 = st.columns(4)

    total_drives = len([d for d in drives if d.espn_result not in ("END OF HALF", "END OF GAME")])
    td_drives = sum(1 for e in evaluated if e.result_exact == "TD")
    fg_drives = sum(1 for e in evaluated if e.result_exact == "FG")
    turnover_drives = sum(1 for e in evaluated if e.result_exact == "Turnover")

    with col1:
        _metric("Total Drives", str(total_drives))
    with col2:
        _metric("Touchdowns", str(td_drives), "#00cc44")
    with col3:
        _metric("Field Goals", str(fg_drives), "#4499ff")
    with col4:
        _metric("Turnovers", str(turnover_drives), "#cc2200")

    st.markdown("#### Last Drive")
    active = [d for d in drives if d.espn_result not in ("END OF GAME",)]
    if active:
        last = active[-1]
        ev = next((e for e in evaluated if e.drive_id == last.drive_id), None)
        _render_last_drive_card(last, ev, game)


def _render_last_drive_card(drive: Drive, ev: EvaluatedDrive | None, game: Game) -> None:
    color_map = resolve_team_colors(
        game.home_team.abbreviation, game.away_team.abbreviation
    )
    team_color = color_map.get(drive.team.abbreviation, "#888888")

    result = ev.result_exact if ev else drive.espn_result or "—"
    cross50 = "Yes" if ev and ev.cross_50 else "No"
    opp35   = "Yes" if ev and ev.opp_35  else "No"
    opp20   = "Yes" if ev and ev.opp_20  else "No"

    st.markdown(
        f"""
        <div style="background:var(--secondary-background-color); border-radius:10px;
                    padding:16px 20px; border-left:4px solid {team_color};">
            <div style="font-size:18px; font-weight:800; margin-bottom:8px;">
                <span style="background:{team_color}; color:{pill_text_color(team_color)};
                             padding:2px 10px; border-radius:6px; margin-right:8px;
                             font-size:14px;">{drive.team.abbreviation}</span>
                {drive.label}
            </div>
            <div style="display:flex; gap:24px; font-size:13px; opacity:0.8;">
                <span><b>Result:</b> {result}</span>
                <span><b>Cross 50:</b> {cross50}</span>
                <span><b>Opp 35:</b> {opp35}</span>
                <span><b>Opp 20:</b> {opp20}</span>
                <span><b>Plays:</b> {drive.play_count}</span>
                <span><b>Yards:</b> {drive.yards_gained}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _metric(label: str, value: str, color: str = "var(--text-color)") -> None:
    st.markdown(
        f'<div style="text-align:center; padding:12px; '
        f'background:var(--secondary-background-color); border-radius:8px;">'
        f'<div style="font-size:11px; opacity:0.6; text-transform:uppercase; '
        f'letter-spacing:0.06em;">{label}</div>'
        f'<div style="font-size:36px; font-weight:800; color:{color};">{value}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
