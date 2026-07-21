from __future__ import annotations
import streamlit as st
from models.drive import Drive, SpecialTeamsScore
from rules.engine import EvaluatedDrive
from qc.comparator import DriveQC
from utils.colors import resolve_team_colors, pill_text_color
from components.tables import render_table
from components.status_badge import drive_status_badge_html

# Make expander labels larger and bolder
_EXPANDER_CSS = """
<style>
details summary p {
    font-size: 15px !important;
    font-weight: 700 !important;
}
</style>
"""


def render(
    drives: list[Drive],
    evaluated: list[EvaluatedDrive],
    drive_qcs: list[DriveQC],
    game_home_abbrev: str,
    game_away_abbrev: str,
    color_mode: bool = True,
    special_teams_scores: list[SpecialTeamsScore] | None = None,
) -> None:
    special_teams_scores = special_teams_scores or []
    if not drives:
        st.info("No drives yet.")
        return

    st.markdown(_EXPANDER_CSS, unsafe_allow_html=True)

    color_map = resolve_team_colors(game_away_abbrev, game_home_abbrev)
    ev_by_id = {e.drive_id: e for e in evaluated}
    qc_by_id = {q.drive_id: q for q in drive_qcs}

    # ── Team filter + sort ───────────────────────────────────────────
    if "drives_team_filter" not in st.session_state:
        st.session_state.drives_team_filter = "All"
    if "drives_newest_first" not in st.session_state:
        st.session_state.drives_newest_first = False

    col_all, col_away, col_home, _, col_sort = st.columns([1, 1, 1, 3, 1.5])
    with col_all:
        if st.button("All", use_container_width=True,
                     type="primary" if st.session_state.drives_team_filter == "All" else "secondary"):
            st.session_state.drives_team_filter = "All"
    with col_away:
        if st.button(game_away_abbrev, use_container_width=True,
                     type="primary" if st.session_state.drives_team_filter == game_away_abbrev else "secondary"):
            st.session_state.drives_team_filter = game_away_abbrev
    with col_home:
        if st.button(game_home_abbrev, use_container_width=True,
                     type="primary" if st.session_state.drives_team_filter == game_home_abbrev else "secondary"):
            st.session_state.drives_team_filter = game_home_abbrev
    with col_sort:
        st.button(
            "↕ Newest First" if not st.session_state.drives_newest_first else "↕ Oldest First",
            use_container_width=True,
            on_click=lambda: st.session_state.update(drives_newest_first=not st.session_state.drives_newest_first),
        )

    st.markdown("")

    # ── Filter & order ───────────────────────────────────────────────
    active_filter = st.session_state.drives_team_filter

    def _keep(team_abbrev: str) -> bool:
        return active_filter == "All" or team_abbrev == active_filter

    # Combine drives and special-teams markers into one chronologically
    # ordered stream. Markers carry a .5 sequence so they slot between drives.
    items: list = [d for d in drives if _keep(d.team.abbreviation)]
    items += [s for s in special_teams_scores if _keep(s.team.abbreviation)]
    items.sort(key=lambda x: x.sequence, reverse=st.session_state.drives_newest_first)

    # ── Drive expanders ──────────────────────────────────────────────
    for item in items:
        if isinstance(item, SpecialTeamsScore):
            _render_special_teams_marker(item, color_map)
            continue

        drive = item
        ev = ev_by_id.get(drive.drive_id)
        qc = qc_by_id.get(drive.drive_id)
        label = _expander_label(drive, ev, game_home_abbrev, game_away_abbrev)

        with st.expander(label, expanded=False):
            if ev:
                _render_drive_header(drive, ev, qc, color_map, color_mode)
                st.divider()
                _render_market_detail(ev, qc, color_mode)
                st.divider()
                _render_play_log(drive, color_mode)
                if ev.warnings:
                    st.divider()
                    _render_warnings(ev.warnings)
            else:
                st.warning("Drive evaluation not available yet.")


def _render_special_teams_marker(score: SpecialTeamsScore, color_map: dict) -> None:
    team_color = color_map.get(score.team.abbreviation, "#555555")
    fg = pill_text_color(team_color)
    label = "Special Teams Safety" if score.espn_result == "SAFETY" else "Special Teams TD"
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:12px; padding:8px 14px;
                    margin:2px 0; border:1px dashed #888; border-radius:7px; opacity:0.9;">
            <div style="background:{team_color}; color:{fg}; padding:2px 10px;
                        border-radius:6px; font-weight:800; font-size:13px;">
                {score.team.abbreviation}
            </div>
            <div style="font-size:14px; font-weight:600;">🏈 {label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _expander_label(
    drive: Drive,
    ev: EvaluatedDrive | None,
    home_abbrev: str,
    away_abbrev: str,
) -> str:
    team = drive.team.abbreviation

    if drive.is_current:
        result_part = "● LIVE"
    elif ev:
        result_part = ev.result_exact
    else:
        result_part = drive.espn_result or "—"

    parts = [f"{team}  Drive {drive.team_drive_number}", result_part,
             f"{drive.play_count} plays", f"{drive.yards_gained} yds"]

    if drive.score_home or drive.score_away:
        parts.append(f"{away_abbrev} {drive.score_away} – {home_abbrev} {drive.score_home}")

    return "  ·  ".join(parts)


def _render_drive_header(
    drive: Drive,
    ev: EvaluatedDrive,
    qc: DriveQC | None,
    color_map: dict,
    color_mode: bool,
) -> None:
    team_color = color_map.get(drive.team.abbreviation, "#555555")
    fg = pill_text_color(team_color)

    live_badge = ""
    if drive.is_current:
        live_badge = (
            '<span style="background:#cc0000; color:#fff; padding:2px 8px; '
            'border-radius:5px; font-size:12px; font-weight:700; margin-left:8px;">● LIVE</span>'
        )

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:14px; padding:10px 0;">
            <div style="background:{team_color}; color:{fg}; padding:3px 14px;
                        border-radius:7px; font-weight:800; font-size:18px;">
                {drive.team.abbreviation}
            </div>
            <div style="font-size:18px; font-weight:700;">{drive.label}{live_badge}</div>
            <div style="margin-left:auto;">{drive_status_badge_html(drive.is_current)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Result", str(ev.result_exact))
    with c2:
        st.metric("Plays", str(drive.play_count))
    with c3:
        st.metric("Yards", str(drive.yards_gained))
    with c4:
        st.metric("T.O.P.", str(drive.time_of_possession) if drive.time_of_possession else "—")


def _render_market_detail(ev: EvaluatedDrive, qc: DriveQC | None, color_mode: bool) -> None:
    st.markdown("**Markets**")
    _render_expected_only(ev)


def _render_expected_only(ev: EvaluatedDrive) -> None:
    rows = [
        {"Market": "Drive Result Granular",     "Result": ev.result_granular},
        {"Market": "Drive Result Exact",        "Result": ev.result_exact},
        {"Market": "Drive Result Grouped",      "Result": ev.result_grouped},
        {"Market": "Drive Crosses 50",          "Result": ev.bool_display(ev.cross_50)},
        {"Market": "Drive Crosses Opposing 35", "Result": ev.bool_display(ev.opp_35)},
        {"Market": "Drive Crosses Opposing 20", "Result": ev.bool_display(ev.opp_20)},
        {"Market": "Sack This Drive",           "Result": ev.bool_display(ev.sack)},
        {"Market": "TD Scorer",                 "Result": ev.td_scorer or "N/A"},
    ]
    if ev.is_nfl:
        rows += [
            {"Market": "20+ Yard Passing Play",  "Result": ev.bool_display(ev.passing_20_plus)},
            {"Market": "10+ Yard Rushing Play",  "Result": ev.bool_display(ev.rushing_10_plus)},
            {"Market": "20+ Yard Play",          "Result": ev.bool_display(ev.play_20_plus)},
            {"Market": "4th Down Conversion",    "Result": ev.bool_display(ev.fourth_down_conversion)},
        ]
    rows += [
        {"Market": "Punt Fair Catch",           "Result": ev.bool_display(ev.fair_catch)},
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
