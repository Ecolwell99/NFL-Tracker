"""
HTML table renderer — ported from NHL tool with QC status pill support added.
"""
from __future__ import annotations
import streamlit as st
from utils.colors import pill_text_color
from qc.status import QCStatus, QC_STATUS_COLOR, QC_STATUS_TEXT_COLOR


def html_table(
    rows: list[dict],
    color_mode: bool = True,
    team_color_map: dict[str, str] | None = None,
    wrap_columns: set[str] | None = None,
) -> str:
    """
    Render rows as an HTML table.

    wrap_columns: column names allowed to wrap onto multiple lines instead of
    being held on one line. Cells default to `white-space:nowrap` so short
    values (Down, Yards, market results) never break mid-value — but that also
    means a long play description would force horizontal scrolling, so the
    Description column opts in here. A wrapping column takes `width:100%` so it
    absorbs the leftover table width and the nowrap columns keep their natural
    size; `min-width` stops it collapsing to nothing on a narrow screen.
    """
    if not rows:
        return ""
    wrap_columns = wrap_columns or set()
    headers = list(rows[0].keys())
    th = "".join(
        f'<th style="padding:6px 14px; text-align:left; border-bottom:2px solid '
        f'var(--secondary-background-color); font-size:12px; color:var(--text-color); '
        f'font-weight:700; white-space:nowrap; text-transform:uppercase; '
        f'letter-spacing:0.04em;">{h}</th>'
        for h in headers
    )
    body = ""
    for i, row in enumerate(rows):
        bg = "rgba(128,128,128,0.04)" if i % 2 == 0 else "rgba(128,128,128,0.10)"
        tds = ""
        for h in headers:
            val = row[h]
            display = _render_cell(str(val), color_mode, team_color_map)
            if h in wrap_columns:
                sizing = ("white-space:normal; overflow-wrap:break-word; "
                          "width:100%; min-width:200px; line-height:1.5;")
            else:
                sizing = "white-space:nowrap;"
            tds += (
                f'<td style="padding:5px 14px; font-size:13px; {sizing} '
                f'vertical-align:top; color:var(--text-color); '
                f'font-weight:500;">{display}</td>'
            )
        body += f'<tr style="background-color:{bg};">{tds}</tr>'
    return (
        '<div style="overflow-x:auto; width:100%;">'
        '<table style="width:100%; border-collapse:collapse;">'
        f'<thead><tr>{th}</tr></thead>'
        f'<tbody>{body}</tbody>'
        '</table></div>'
    )


def _render_cell(
    val: str,
    color_mode: bool,
    team_color_map: dict[str, str] | None,
) -> str:
    if not color_mode:
        return val

    # QC status pills
    for status in QCStatus:
        if val == status.value:
            bg = QC_STATUS_COLOR[status]
            fg = QC_STATUS_TEXT_COLOR[status]
            return _pill(val, bg, fg)

    # Yes / No pills
    if val == "Yes":
        return _pill("Yes", "#00cc44", "#000000")
    if val == "No":
        return _pill("No", "#cc2200", "#ffffff")
    if val == "N/A":
        return _pill("N/A", "#444444", "#ffffff")

    # Team color pills
    if team_color_map:
        for abbrev, color in team_color_map.items():
            if abbrev in val:
                return _pill(val, color, pill_text_color(color))

    return val


def _pill(text: str, bg: str, fg: str) -> str:
    return (
        f'<span style="background-color:{bg}; color:{fg}; padding:2px 10px; '
        f'border-radius:12px; font-weight:700; font-size:12px; '
        f'white-space:nowrap;">{text}</span>'
    )


def render_table(rows: list[dict], color_mode: bool = True,
                 team_color_map: dict[str, str] | None = None,
                 wrap_columns: set[str] | None = None) -> None:
    """Render html_table directly into Streamlit."""
    html = html_table(rows, color_mode, team_color_map, wrap_columns)
    if html:
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.info("No data.")
