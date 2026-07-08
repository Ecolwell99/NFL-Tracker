from __future__ import annotations
import streamlit as st
from models.drive import Drive
from rules.engine import EvaluatedDrive
from qc.comparator import DriveQC
from qc.status import QCStatus
from utils.colors import resolve_team_colors, pill_text_color
from components.tables import render_table
from components.status_badge import status_badge_html, mismatch_count_html


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
    ev_by_id  = {e.drive_id: e for e in evaluated}
    qc_by_id  = {q.drive_id: q for q in drive_qcs}

    # Drive selector
    drive_labels = [d.label for d in drives]
    selected_label = st.selectbox(
        "Select Drive", options=drive_labels, index=len(drive_labels) - 1,
        label_visibility="collapsed",
    )
    selected_drive = next(d for d in drives if d.label == selected_label)
    ev  = ev_by_id.get(selected_drive.drive_id)
    qc  = qc_by_id.get(selected_drive.drive_id)

    if ev:
        _render_drive_header(selected_drive, ev, qc, color_map, color_mode)
        st.divider()
        _render_market_detail(ev, qc, color_mode)
        st.divider()
        _render_play_log(selected_drive, color_mode)
        if ev.warnings:
            st.divider()
            _render_warnings(ev.warnings)
    else:
        st.warning("Drive evaluation not available yet.")


def _render_drive_header(
    drive: Drive,
    ev: EvaluatedDrive,
    qc: DriveQC | None,
    color_map: dict,
    color_mode: bool,
) -> None:
    team_color = color_map.get(drive.team.abbreviation, "#555555")
    fg = pill_text_color(team_color)
    overall = qc.overall_status if qc else QCStatus.PENDING

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:16px; padding:12px 0;">
            <div style="background:{team_color}; color:{fg}; padding:4px 16px;
                        border-radius:8px; font-weight:800; font-size:20px;">
                {drive.team.abbreviation}
            </div>
            <div style="font-size:20px; font-weight:700;">{drive.label}</div>
            <div style="margin-left:auto;">{status_badge_html(overall)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Result", str(ev.result_exact))
    with c2:
        st.metric("Plays", str(drive.play_count))
    with c3:
        st.metric("Yards", str(drive.yards_gained))
    with c4:
        start = f"Own {100 - drive.start_yardline}" if drive.start_yardline > 50 else f"Opp {drive.start_yardline}"
        st.metric("Start", str(start))
    with c5:
        st.metric("T.O.P.", str(drive.time_of_possession) if drive.time_of_possession else "—")


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
        # No system results yet — show expected only
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
