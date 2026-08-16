from __future__ import annotations
import streamlit as st
from models.drive import Drive
from utils.colors import resolve_team_colors, pill_text_color, team_fallback_colors
from components.tables import render_table

# Fixed list — the play types traders filter on. Module level so the filter row
# below stays readable.
_PLAY_TYPE_FILTERS = [
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


def render(
    drives: list[Drive],
    game_home_abbrev: str,
    game_away_abbrev: str,
    filter_recent: bool = False,
    color_mode: bool = True,
    use_curated_colors: bool = True,
) -> None:
    if not drives:
        st.info("No play data yet.")
        return

    color_map = resolve_team_colors(
        game_away_abbrev, game_home_abbrev,
        fallback=team_fallback_colors(*{d.team.abbreviation: d.team for d in drives}.values()),
        use_curated=use_curated_colors,
    )

    # ── Filter controls + sort ───────────────────────────────────────
    # Sort button on the right of the same row, mirroring the Drives tab.
    all_teams = sorted({d.team.abbreviation for d in drives})
    col_team, col_type, col_sort = st.columns([3, 3, 1.5])

    with col_team:
        team_filter = st.multiselect(
            "Filter by team", options=["All"] + all_teams, default=["All"],
            label_visibility="collapsed",
        )
    with col_type:
        type_filter = st.multiselect(
            "Filter by play type", options=["All"] + _PLAY_TYPE_FILTERS, default=["All"],
            label_visibility="collapsed",
        )
    with col_sort:
        # Label is the ACTION, matching the Drives tab: it reads "Newest First"
        # while currently oldest-first. on_click (not an `if st.button()` body)
        # so the state flips before the rerun — otherwise the order lags one
        # click behind. The button's own label changes, so it carries a static
        # key: a button holds no state of its own, but the key keeps its
        # identity stable rather than being derived from the changing label.
        st.button(
            "↕ Newest First" if not filter_recent else "↕ Oldest First",
            use_container_width=True,
            key="pbp_sort_toggle",
            on_click=lambda: st.session_state.update(
                filter_recent=not st.session_state.filter_recent
            ),
        )

    rows = []
    for drive in drives:
        # Filter first — no point building a pill for a drive we then skip.
        if "All" not in team_filter and drive.team.abbreviation not in team_filter:
            continue

        team_color = color_map.get(drive.team.abbreviation, "#555")
        fg = pill_text_color(team_color)
        team_pill = (
            f'<span style="background:{team_color}; color:{fg}; padding:1px 7px; '
            f'border-radius:4px; font-size:11px; font-weight:700;">'
            f'{drive.team.abbreviation}</span>'
        )

        # One column instead of two: drive.label is the full team name
        # ("Chicago Bears Drive 1"), which just repeated the Team column's
        # abbreviation and ate width the description needs.
        drive_cell = f"{team_pill} Drive {drive.team_drive_number}"

        for play in drive.plays:
            if "All" not in type_filter and play.play_type.value not in type_filter:
                continue
            rows.append({
                "Drive":    drive_cell,
                "Down":     f"{play.down} & {play.distance}" if play.down > 0 else "—",
                "Type":     play.play_type.value,
                "Yards":    str(play.yards),
                "Scoring":  "Yes" if play.is_scoring else "No",
                # Never truncate — traders have to read the whole description,
                # penalty text especially. The Description column wraps instead.
                "Description": play.description,
            })

    # Newest first. Drives arrive in game order and plays are chronological within
    # a drive, so reversing the flat row list reverses BOTH levels at once and
    # gives strict reverse-chronological order — the latest play on top.
    if filter_recent:
        rows = list(reversed(rows))

    if rows:
        render_table(rows, color_mode=False, wrap_columns={"Description"})
    else:
        st.info("No plays match the current filter.")
