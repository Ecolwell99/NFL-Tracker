"""
Markets tab — core QC view.

Layout: two team sections (away, then home). Within each section,
rows = markets, columns = drives for that team only.
Pending cells show plain text (no pill). Only Match / Mismatch get color.
"""
from __future__ import annotations
import streamlit as st
from rules.engine import EvaluatedDrive
from qc.comparator import DriveQC
from qc.status import QCStatus, QC_STATUS_COLOR, QC_STATUS_TEXT_COLOR
from utils.colors import resolve_team_colors, pill_text_color

_UNIVERSAL_MARKETS = [
    "Drive Result Granular",
    "Drive Result Exact",
    "Drive Result Grouped",
    "Drive Crosses 50",
    "Drive Crosses Opposing 35",
    "Drive Crosses Opposing 20",
    "Sack This Drive",
    "Punt Fair Catch",
    "TD Scorer",
]

_NFL_MARKETS = [
    "20+ Yard Passing Play",
    "10+ Yard Rushing Play",
    "20+ Yard Play",
    "4th Down Conversion",
]


def render(
    evaluated: list[EvaluatedDrive],
    drive_qcs: list[DriveQC],
    game_home_abbrev: str,
    game_away_abbrev: str,
    is_nfl: bool = True,
    color_mode: bool = True,
    show_void: bool = True,
) -> None:
    if not evaluated:
        st.info("No drive data yet. Load a game and start tracking.")
        return

    markets = _UNIVERSAL_MARKETS + (_NFL_MARKETS if is_nfl else [])

    display_evs = evaluated
    display_qcs = drive_qcs
    if not show_void:
        display_evs = [e for e in evaluated if e.result_exact != "Void"]
        display_qcs = [q for q in drive_qcs if q.drive_id in {e.drive_id for e in display_evs}]

    if not display_evs:
        st.info("No non-void drives yet.")
        return

    _render_summary_bar(display_qcs)
    st.markdown("")

    color_map = resolve_team_colors(game_away_abbrev, game_home_abbrev)

    away_evs = [e for e in display_evs if e.team_abbrev == game_away_abbrev]
    home_evs = [e for e in display_evs if e.team_abbrev == game_home_abbrev]
    qc_by_drive = {q.drive_id: q for q in display_qcs}

    for team_abbrev, team_evs in [(game_away_abbrev, away_evs), (game_home_abbrev, home_evs)]:
        if not team_evs:
            continue
        team_color = color_map.get(team_abbrev, "#555555")
        fg = pill_text_color(team_color)
        _render_team_header(team_abbrev, team_color, fg)
        _render_market_grid(markets, team_evs, qc_by_drive, color_mode)
        st.markdown("")


def _render_team_header(abbrev: str, bg: str, fg: str) -> None:
    st.markdown(
        f'<div style="background:{bg}; color:{fg}; padding:8px 16px; '
        f'border-radius:8px; font-size:14px; font-weight:800; '
        f'letter-spacing:0.06em; margin-bottom:6px; display:inline-block;">'
        f'{abbrev}</div>',
        unsafe_allow_html=True,
    )


def _render_summary_bar(drive_qcs: list[DriveQC]) -> None:
    total = len(drive_qcs)
    mismatches = sum(q.mismatch_count for q in drive_qcs)
    pending_drives = sum(1 for q in drive_qcs if q.pending_count > 0 and q.mismatch_count == 0)
    clean = sum(1 for q in drive_qcs if q.overall_status == QCStatus.MATCH)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _mini_metric("Drives", str(total))
    with c2:
        _mini_metric("Clean", str(clean), "#00cc44")
    with c3:
        _mini_metric("Mismatches", str(mismatches), "#cc2200" if mismatches else "#00cc44")
    with c4:
        _mini_metric("Pending", str(pending_drives), "#ccaa00" if pending_drives else "var(--text-color)")


def _render_market_grid(
    markets: list[str],
    team_evs: list[EvaluatedDrive],
    qc_by_drive: dict[str, DriveQC],
    color_mode: bool,
) -> None:
    header_cells = '<th style="' + _th_style() + ' min-width:180px;">Market</th>'
    for ev in team_evs:
        header_cells += (
            f'<th style="{_th_style()} min-width:110px; text-align:center;">'
            f'Drive {ev.team_drive_number}'
            f'</th>'
        )

    body_rows = ""
    for i, market in enumerate(markets):
        row_bg = "rgba(128,128,128,0.04)" if i % 2 == 0 else "rgba(128,128,128,0.10)"
        cells = (
            f'<td style="{_td_style()} font-weight:600; opacity:0.85; '
            f'font-size:12px;">{market}</td>'
        )
        for ev in team_evs:
            expected = _get_expected(ev, market)
            qc = qc_by_drive.get(ev.drive_id)
            status = _get_status(qc, market) if qc else QCStatus.PENDING
            system = _get_system(qc, market) if qc else ""
            cells += f'<td style="{_td_style()} text-align:center;">'
            cells += _cell_content(expected, status, system, color_mode)
            cells += '</td>'
        body_rows += f'<tr style="background:{row_bg};">{cells}</tr>'

    html = (
        '<div style="overflow-x:auto; width:100%;">'
        '<table style="width:100%; border-collapse:collapse; font-family:monospace;">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{body_rows}</tbody>'
        '</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _cell_content(expected: str, status: QCStatus, system: str, color_mode: bool) -> str:
    if not color_mode:
        return f'<span style="font-size:12px;">{expected}</span>'

    if status == QCStatus.NOT_APPLICABLE:
        return '<span style="font-size:11px; opacity:0.3;">N/A</span>'

    if status == QCStatus.PENDING:
        return f'<span style="font-size:12px;">{expected}</span>'

    bg = QC_STATUS_COLOR.get(status, "#888888")
    fg = QC_STATUS_TEXT_COLOR.get(status, "#ffffff")

    if status == QCStatus.MISMATCH:
        return (
            f'<span style="background:{bg}; color:{fg}; padding:2px 8px; '
            f'border-radius:6px; font-size:11px; font-weight:700; display:inline-block;">'
            f'EXP: {expected}<br>'
            f'<span style="font-weight:400; font-size:10px;">SYS: {system}</span>'
            f'</span>'
        )

    return (
        f'<span style="background:{bg}; color:{fg}; padding:2px 8px; '
        f'border-radius:6px; font-size:11px; font-weight:700; '
        f'display:inline-block;">{expected}</span>'
    )


def _get_expected(ev: EvaluatedDrive, market: str) -> str:
    _MAP = {
        "Drive Result Granular":      ev.result_granular,
        "Drive Result Exact":         ev.result_exact,
        "Drive Result Grouped":       ev.result_grouped,
        "Drive Crosses 50":           ev.bool_display(ev.cross_50),
        "Drive Crosses Opposing 35":  ev.bool_display(ev.opp_35),
        "Drive Crosses Opposing 20":  ev.bool_display(ev.opp_20),
        "Sack This Drive":            ev.bool_display(ev.sack),
        "Punt Fair Catch":            ev.bool_display(ev.fair_catch),
        "TD Scorer":                  ev.td_scorer or "N/A",
        "20+ Yard Passing Play":      ev.bool_display(ev.passing_20_plus),
        "10+ Yard Rushing Play":      ev.bool_display(ev.rushing_10_plus),
        "20+ Yard Play":              ev.bool_display(ev.play_20_plus),
        "4th Down Conversion":        ev.bool_display(ev.fourth_down_conversion),
    }
    return _MAP.get(market, "—")


def _get_status(qc: DriveQC, market: str) -> QCStatus:
    for r in qc.results:
        if r.market == market:
            return r.status
    return QCStatus.PENDING


def _get_system(qc: DriveQC, market: str) -> str:
    for r in qc.results:
        if r.market == market:
            return r.system
    return ""


def _th_style() -> str:
    return (
        "padding:8px 12px; text-align:left; border-bottom:2px solid "
        "var(--secondary-background-color); font-size:11px; "
        "color:var(--text-color); font-weight:700; white-space:nowrap; "
        "text-transform:uppercase; letter-spacing:0.04em; "
        "position:sticky; top:0; background:var(--background-color); z-index:1;"
    )


def _td_style() -> str:
    return "padding:5px 10px; font-size:13px; white-space:nowrap; color:var(--text-color);"


def _mini_metric(label: str, value: str, color: str = "var(--text-color)") -> None:
    st.markdown(
        f'<div style="text-align:center; padding:10px; '
        f'background:var(--secondary-background-color); border-radius:8px;">'
        f'<div style="font-size:10px; opacity:0.6; text-transform:uppercase; '
        f'letter-spacing:0.06em;">{label}</div>'
        f'<div style="font-size:28px; font-weight:800; color:{color};">{value}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
