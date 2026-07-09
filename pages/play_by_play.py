from __future__ import annotations
import streamlit as st
from models.drive import Drive
from utils.colors import resolve_team_colors, pill_text_color
from components.tables import render_table


def render(
    drives: list[Drive],
    game_home_abbrev: str,
    game_away_abbrev: str,
    filter_recent: bool = False,
    color_mode: bool = True,
) -> None:
    if not drives:
        st.info("No play data yet.")
        return

    color_map = resolve_team_colors(game_away_abbrev, game_home_abbrev)

    # Filter controls
    all_teams = sorted({d.team.abbreviation for d in drives})
    team_filter = st.multiselect(
        "Filter by team", options=["All"] + all_teams, default=["All"],
        label_visibility="collapsed",
    )

    PLAY_TYPE_FILTERS = [
        "Fumble",
        "Field Goal Good",
        "Field Goal Missed",
        "Pass Incompletion",
        "Pass Interception Return",
        "Pass Reception",
        "Passing Touchdown",
        "Penalty",
        "Punt",
        "Rush",
        "Sack",
    ]
    type_filter = st.multiselect(
        "Filter by play type", options=["All"] + PLAY_TYPE_FILTERS, default=["All"],
        label_visibility="collapsed",
    )

    rows = []
    for drive in drives:
        team_color = color_map.get(drive.team.abbreviation, "#555")
        fg = pill_text_color(team_color)
        team_pill = (
            f'<span style="background:{team_color}; color:{fg}; padding:1px 7px; '
            f'border-radius:4px; font-size:11px; font-weight:700;">'
            f'{drive.team.abbreviation}</span>'
        )

        if "All" not in team_filter and drive.team.abbreviation not in team_filter:
            continue

        for play in drive.plays:
            if "All" not in type_filter and play.play_type.value not in type_filter:
                continue
            rows.append({
                "Drive":    drive.label,
                "Team":     drive.team.abbreviation,
                "Down":     f"{play.down} & {play.distance}" if play.down > 0 else "—",
                "Type":     play.play_type.value,
                "Yards":    str(play.yards),
                "Scoring":  "Yes" if play.is_scoring else "No",
                "Description": play.description[:90] + ("…" if len(play.description) > 90 else ""),
            })

    if filter_recent:
        rows = list(reversed(rows))

    if rows:
        render_table(rows, color_mode=False)
    else:
        st.info("No plays match the current filter.")
