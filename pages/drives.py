from __future__ import annotations
import streamlit as st
from models.drive import Drive
from rules.engine import EvaluatedDrive
from qc.comparator import DriveQC
from qc.status import QCStatus
from utils.colors import resolve_team_colors, pill_text_color
from components.tables import render_table
from components.status_badge import status_badge_html


def render(
    drives: list[Drive],
    evaluated: list[EvaluatedDrive],
    drive_qcs: list[DriveQC],
    game_home_abbrev: str,
    game_away_abbrev: str,
    color_mode: bool = True,
) -> None:
    if not drives:
        st.info("No drives yet.")
        return

    color_map = resolve_team_colors(game_away_abbrev, game_home_abbrev)
    ev_by_id = {e.drive_id: e for e in evaluated}
    qc_by_id = {q.drive_id: q for q in drive_qcs}

    # ── Team filter ──────────────────────────────────────────────────
    if "drives_team_filter" not in st.session_state:
        st.session_state.drives_team_filter = "All"

    col_all, col_away, col_home, _ = st.columns([1, 1, 1, 5])
    with col_all:
        if st.button("All", use_container_width=True,
                     type="primary" if st.session_state.drives_team_filter == "All" else "secondary"):
            st.session_state.drives_team_filter = "All"
    with col_away:
        away_color = color_map.get(game_away_abbrev, "#555")
        if st.button(game_away_abbrev, use_container_width=True,
                     type="primary" if st.session_state.drives_team_filter == game_away_abbrev else "secondary"):
            st.session_state.drives_team_filter = game_away_abbrev
    with col_home:
        if st.button(game_home_abbrev, use_container_width=True,
                     type="primary" if st.session_state.drives_team_filter == game_home_abbrev else "secondary"):
            st.session_state.drives_team_filter = game_home_abbrev

    st.markdown("")

    # ── Filter & order ───────────────────────────────────────────────
    active_filter = st.session_state.drives_team_filter
    filtered = sorted(
        [d for d in drives if active_filter == "All" or d.team.abbreviation == active_filter],
        key=lambda d: d.sequence,
    )

    # ── Drive cards ──────────────────────────────────────────────────
    for drive in filtered:
        ev = ev_by_id.get(drive.drive_id)
        qc = qc_by_id.get(drive.drive_id)
        _render_drive_card(drive, ev, qc, color_map, game_home_abbrev, game_away_abbrev, color_mode)


def _render_drive_card(
    drive: Drive,
    ev: EvaluatedDrive | None,
    qc: DriveQC | None,
    color_map: dict,
    home_abbrev: str,
    away_abbrev: str,
    color_mode: bool,
) -> None:
    key = f"drive_open_{drive.drive_id}"
    if key not in st.session_state:
        st.session_state[key] = False

    team_abbrev = drive.team.abbreviation
    team_color = color_map.get(team_abbrev, "#555555")
    fg = pill_text_color(team_color)

    # Result text
    if drive.is_current:
        result_text = "● LIVE"
        result_color = "#ff4444"
    elif ev:
        result_text = ev.result_exact
        result_color = "var(--text-color)"
    else:
        result_text = drive.espn_result or "—"
        result_color = "var(--text-color)"

    # Score
    if drive.score_home or drive.score_away:
        score_html = (
            f'<span style="font-size:12px; font-weight:600; opacity:0.85;">'
            f'<span style="color:{color_map.get(away_abbrev, "#aaa")}; font-weight:800;">{away_abbrev}</span>'
            f' {drive.score_away} &nbsp;–&nbsp; '
            f'<span style="color:{color_map.get(home_abbrev, "#aaa")}; font-weight:800;">{home_abbrev}</span>'
            f' {drive.score_home}</span>'
        )
    else:
        score_html = ""

    chevron = "▲" if st.session_state[key] else "▼"

    st.markdown(
        f"""
        <div style="
            border:1px solid rgba(128,128,128,0.2);
            border-radius:7px;
            padding:7px 14px;
            margin-bottom:4px;
            background:var(--secondary-background-color);
        ">
            <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
                <div style="
                    background:{team_color}; color:{fg};
                    padding:2px 10px; border-radius:5px;
                    font-weight:800; font-size:13px; letter-spacing:0.03em;
                ">{team_abbrev}</div>
                <div style="font-size:13px; font-weight:600; opacity:0.9;">
                    Drive {drive.team_drive_number}
                </div>
                <div style="font-size:13px; font-weight:800; color:{result_color};">
                    {result_text}
                </div>
                <div style="font-size:12px; opacity:0.6;">
                    {drive.play_count} plays &nbsp;·&nbsp; {drive.yards_gained} yds
                </div>
                {f'<div style="margin-left:auto;">{score_html}</div>' if score_html else ''}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(f"{chevron} {'Hide' if st.session_state[key] else 'Show'} detail",
                 key=f"btn_{drive.drive_id}",
                 use_container_width=False):
        st.session_state[key] = not st.session_state[key]
        st.rerun()

    if st.session_state[key]:
        with st.container():
            if ev:
                _render_market_detail(ev, qc, color_mode)
                st.divider()
                _render_play_log(drive, color_mode)
                if ev.warnings:
                    st.divider()
                    _render_warnings(ev.warnings)
            else:
                st.warning("Drive evaluation not available yet.")
        st.markdown("")


def _render_market_detail(ev: EvaluatedDrive, qc: DriveQC | None, color_mode: bool) -> None:
    st.markdown("**Markets**")
    rows = []
    for result in (qc.results if qc else []):
        rows.append({
            "Market":   result.market,
            "Expected": result.expected,
            "System":   result.system or "—",
            "Status":   result.status.value,
        })
    if rows:
        render_table(rows, color_mode)
    else:
        _render_expected_only(ev)


def _render_expected_only(ev: EvaluatedDrive) -> None:
    rows = [
        {"Market": "Drive Result Granular",     "Expected": ev.result_granular},
        {"Market": "Drive Result Exact",        "Expected": ev.result_exact},
        {"Market": "Drive Result Grouped",      "Expected": ev.result_grouped},
        {"Market": "Drive Crosses 50",          "Expected": ev.bool_display(ev.cross_50)},
        {"Market": "Drive Crosses Opposing 35", "Expected": ev.bool_display(ev.opp_35)},
        {"Market": "Drive Crosses Opposing 20", "Expected": ev.bool_display(ev.opp_20)},
        {"Market": "Sack This Drive",           "Expected": ev.bool_display(ev.sack)},
        {"Market": "Punt Fair Catch",           "Expected": ev.bool_display(ev.fair_catch)},
        {"Market": "TD Scorer",                 "Expected": ev.td_scorer or "N/A"},
    ]
    if ev.is_nfl:
        rows += [
            {"Market": "20+ Yard Passing Play",  "Expected": ev.bool_display(ev.passing_20_plus)},
            {"Market": "10+ Yard Rushing Play",  "Expected": ev.bool_display(ev.rushing_10_plus)},
            {"Market": "20+ Yard Play",          "Expected": ev.bool_display(ev.play_20_plus)},
            {"Market": "4th Down Conversion",    "Expected": ev.bool_display(ev.fourth_down_conversion)},
        ]
    render_table(rows, color_mode=False)


def _render_play_log(drive: Drive, color_mode: bool) -> None:
    st.markdown("**Play-by-Play**")
    if not drive.plays:
        st.info("No play data for this drive.")
        return
    rows = []
    for play in drive.plays:
        rows.append({
            "Down":   f"{play.down} & {play.distance}" if play.down > 0 else "—",
            "Type":   play.play_type.value,
            "Yards":  str(play.yards),
            "Pos":    f"{'Opp' if play.yard_line <= 50 else 'Own'} {abs(50 - play.yard_line) + 50 if play.yard_line > 50 else play.yard_line}",
            "Description": play.description[:80] + ("…" if len(play.description) > 80 else ""),
        })
    render_table(rows, color_mode=False)


def _render_warnings(warnings: list[str]) -> None:
    st.markdown("**Warnings**")
    for w in warnings:
        st.markdown(
            f'<div style="background:#3a1600; color:#ffd966; border:1px solid #ff9900; '
            f'padding:8px 14px; border-radius:6px; margin-bottom:6px; font-size:13px;">⚠ {w}</div>',
            unsafe_allow_html=True,
        )
