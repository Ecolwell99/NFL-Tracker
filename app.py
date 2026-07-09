import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from state.session import init_state, reset_game_state
from services.espn_provider import ESPNProvider, RateLimitedError
from services.cache import cached_get_games, cached_get_drives, cached_get_game
from models.game import League
from rules.engine import evaluate_all_drives
from qc.comparator import compare_all_drives
from qc.corrections import snapshot_all_drives, diff_drives, build_drive_label_map, merge_corrections
from components.warning_box import warning_box
from utils.time import period_label
from utils.colors import resolve_team_colors

import pages.overview        as pg_overview
import pages.drives          as pg_drives
import pages.play_by_play    as pg_pbp
import pages.stat_corrections as pg_corrections

# ── App config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="NFL Markets QC",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* Tighten default Streamlit padding */
.block-container { padding-top: 1rem; padding-bottom: 1rem; }
/* Remove red underline from metric delta */
[data-testid="stMetricDelta"] svg { display: none; }
</style>
""", unsafe_allow_html=True)

init_state()

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## NFL Markets QC")
    st.divider()

    # Game selector
    if st.button("Load Live Games", use_container_width=True):
        try:
            games = cached_get_games()
            st.session_state.games = games
            if not games:
                st.info("No live games right now.")
            else:
                labels = [g.label for g in games]
                if st.session_state.selected_game_label not in labels:
                    st.session_state.selected_game_label = labels[0]
                    st.session_state.selected_game_id    = games[0].game_id
                st.success(f"{len(games)} game(s) loaded.")
        except Exception as e:
            st.error(f"Error: {e}")

    game_labels = [g.label for g in st.session_state.games]
    selected_label = st.selectbox(
        "Game",
        options=game_labels,
        index=game_labels.index(st.session_state.selected_game_label)
              if st.session_state.selected_game_label in game_labels else None,
        placeholder="Load games first",
        label_visibility="collapsed",
    )
    if selected_label and selected_label != st.session_state.selected_game_label:
        st.session_state.selected_game_label = selected_label
        for g in st.session_state.games:
            if g.label == selected_label:
                st.session_state.selected_game_id = g.game_id
                reset_game_state()
                break

    st.divider()

    manual_id = st.text_input("Manual Game ID", placeholder="e.g. 401772912",
                               label_visibility="collapsed")
    if st.button("Load Manual ID", use_container_width=True):
        if manual_id.strip().isdigit():
            gid = manual_id.strip()
            if gid != st.session_state.selected_game_id:
                st.session_state.selected_game_id    = gid
                st.session_state.selected_game_label = f"Manual ({gid})"
                reset_game_state()
            st.success(f"Game ID {gid} loaded.")
        else:
            st.error("Enter a numeric game ID.")

    st.divider()

    if st.button("▶  Track Game", use_container_width=True, type="primary"):
        if not st.session_state.selected_game_id:
            st.warning("Select a game first.")
        else:
            st.session_state.tracking = True
            st.session_state.drive_snapshots = {}

    # Display prefs
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(
            "🎨 Color ON" if st.session_state.color_mode else "🎨 Color OFF",
            use_container_width=True,
        ):
            st.session_state.color_mode = not st.session_state.color_mode
    with col_b:
        if st.button(
            "↕ New→Old" if st.session_state.filter_recent else "↕ Old→New",
            use_container_width=True,
        ):
            st.session_state.filter_recent = not st.session_state.filter_recent

    st.divider()

    # Connection status
    if st.session_state.tracking:
        now_et = datetime.now(ZoneInfo("America/New_York")).strftime("%I:%M:%S %p ET")
        st.markdown(
            f'<div style="font-size:12px; opacity:0.6;">Last refresh: {now_et}</div>',
            unsafe_allow_html=True,
        )
        refresh_secs = st.session_state.refresh_interval_ms // 1000
        st.markdown(
            f'<div style="font-size:12px; opacity:0.6;">Interval: {refresh_secs}s</div>',
            unsafe_allow_html=True,
        )

# ── Main area ────────────────────────────────────────────────────────
if not st.session_state.tracking:
    warning_box("STATUS: OK — Load a game and click Track Game", "ok")
    st.stop()

# Auto-refresh
st_autorefresh(
    interval=st.session_state.refresh_interval_ms,
    key="nfl_qc_refresh",
)

# Rate-limit cooldown (mirrors NHL tool)
if st.session_state.rate_limit_skip_remaining > 0:
    st.session_state.rate_limit_skip_remaining -= 1
    secs_left = st.session_state.rate_limit_skip_remaining * (
        st.session_state.refresh_interval_ms // 1000
    )
    warning_box(f"⚠ RATE LIMITED — resuming in ~{secs_left}s", "alert")
    st.stop()

# ── Data fetch & evaluation ──────────────────────────────────────────
try:
    game_id = st.session_state.selected_game_id
    game    = cached_get_game(game_id)
    drives  = cached_get_drives(game_id)

    evaluated = evaluate_all_drives(drives, League.NFL)
    drive_qcs = compare_all_drives(
        evaluated,
        st.session_state.system_results,
    )

    # Stat correction detection
    detected_at = datetime.now(ZoneInfo("America/New_York")).strftime("%I:%M:%S %p ET")
    prev_snaps  = st.session_state.drive_snapshots
    curr_snaps  = snapshot_all_drives(drives)
    label_map   = build_drive_label_map(drives)

    if prev_snaps:
        new_corrections = diff_drives(prev_snaps, curr_snaps, label_map, detected_at)
        if new_corrections:
            st.session_state.stat_corrections = merge_corrections(
                st.session_state.stat_corrections, new_corrections
            )
            st.session_state.warning_message  = (
                f"⚠ {len(new_corrections)} stat correction(s) detected at {detected_at}"
            )
            st.session_state.warning_type     = "alert"
            st.session_state.alert_shown_until = time.time() + 10

    st.session_state.drive_snapshots = curr_snaps
    st.session_state.current_drives  = drives
    st.session_state.evaluated_drives = evaluated
    st.session_state.drive_qcs        = drive_qcs

    # Auto-clear alert after timeout
    if time.time() >= st.session_state.alert_shown_until:
        st.session_state.warning_message = "STATUS: OK"
        st.session_state.warning_type    = "ok"

except RateLimitedError:
    st.session_state.rate_limit_skip_remaining = 2
    st.session_state.warning_message  = "⚠ RATE LIMITED — brief cooldown"
    st.session_state.warning_type     = "alert"
    st.session_state.alert_shown_until = time.time() + 15
    warning_box(st.session_state.warning_message, "alert")
    st.stop()
except Exception as e:
    warning_box(f"⚠ Refresh error: {e}", "alert")
    st.stop()

# ── Status bar ───────────────────────────────────────────────────────
warning_box(st.session_state.warning_message, st.session_state.warning_type)

# ── Tab navigation ───────────────────────────────────────────────────
correction_total = len(st.session_state.stat_corrections)

tab_labels = [
    "Overview",
    "Drives",
    "Play-by-Play",
    f"Corrections {'🔴' if correction_total else '✅'} ({correction_total})",
]

tabs = st.tabs(tab_labels)

with tabs[0]:
    pg_overview.render(game, drives, evaluated)

with tabs[1]:
    pg_drives.render(
        drives, evaluated, drive_qcs,
        game_home_abbrev=game.home_team.abbreviation,
        game_away_abbrev=game.away_team.abbreviation,
        color_mode=st.session_state.color_mode,
    )

with tabs[2]:
    pg_pbp.render(
        drives,
        game_home_abbrev=game.home_team.abbreviation,
        game_away_abbrev=game.away_team.abbreviation,
        filter_recent=st.session_state.filter_recent,
        color_mode=st.session_state.color_mode,
    )

with tabs[3]:
    pg_corrections.render(
        st.session_state.stat_corrections,
        color_mode=st.session_state.color_mode,
    )
