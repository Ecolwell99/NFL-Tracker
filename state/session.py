"""
Session state management — direct port of the NHL tool's init_state() pattern.

All Streamlit session state keys are declared here with typed defaults.
Increment STATE_VERSION whenever the shape of state changes to force a reset.
"""
from __future__ import annotations
import streamlit as st
from models.game import League

# 3: dropped the dead "selected_tab" key (left over from the removed Markets tab)
#    and added "active_tab", which drives the tab strip in app.py.
# 4: added the five corr_*_filter keys for the Corrections tab filter row.
# 5: Team/Type/Play filters became multiselects — their values are now LISTS, not
#    strings, and corr_market_filter was removed. The shape change is why this
#    bump matters: a session holding "All" would break list membership tests.
STATE_VERSION = 5

_DEFAULTS: dict = {
    # League selection
    "league":                   League.NFL, # League enum

    # Game selection
    "games":                    [],         # list[Game]
    "selected_game_id":         None,       # str | None
    "selected_game_label":      None,       # str | None
    "tracking":                 False,

    # Live data (refreshed each cycle)
    "current_drives":           [],         # list[Drive]
    "evaluated_drives":         [],         # list[EvaluatedDrive]
    "drive_qcs":                [],         # list[DriveQC]

    # QC system results — entered manually by trader
    # Structure: drive_id → {market_name → system_value}
    "system_results":           {},

    # Stat correction monitoring
    "drive_snapshots":          {},         # drive_id → snapshot dict (previous cycle)
    "stat_corrections":         [],         # list[StatCorrection] (running log)

    # Alert system (mirrors NHL tool exactly)
    "warning_message":          "STATUS: OK",
    "warning_type":             "ok",
    "alert_shown_until":        0.0,
    "alert_log":                [],

    # Rate limiting (mirrors NHL tool exactly)
    "rate_limit_skip_remaining": 0,

    # UI preferences
    "filter_recent":            False,
    "color_mode":               True,
    # Which tab is showing. Held in session state (not by st.tabs, which keeps it
    # frontend-side only) so the autorefresh rerun can't bounce you back to
    # Drives. Values are the stable keys in app.py: "drives" | "pbp" |
    # "corrections". Deliberately NOT reset by reset_game_state — switching game
    # or league should leave you on the tab you were working in.
    "active_tab":               "drives",

    # Corrections tab filters. Persist across refresh cycles (so a filter set
    # mid-game holds) but ARE cleared by reset_game_state — a filter left over
    # from the previous game would silently hide the new game's corrections.
    # Impact is single-select (its options are mutually exclusive). Team/Type/Play
    # are multiselect LISTS where empty = no filter, so the defaults must be []
    # and NOT "All" — a string default would break the list logic in the page.
    # Mutable defaults are copied on assignment below.
    "corr_impact_filter":       "All",     # All | Market Impacted | No Impact
    "corr_team_filter":         [],        # [] = all | [away abbrev, home abbrev]
    "corr_field_filter":        [],        # [] = all | StatCorrection.field values
    "corr_play_filter":         [],        # [] = all | Rush and/or Pass

    "refresh_interval_ms":      5000,
    "show_nfl_only_markets":    True,
    "show_void_drives":         True,
}


def _default(key: str):
    """
    A FRESH copy of a default value. Several defaults are mutable ([] and {}), and
    assigning them directly would alias the single object inside _DEFAULTS — so
    anything mutating session state in place (a multiselect's list, a dict of
    system results) would corrupt the default for every later reset.
    """
    value = _DEFAULTS[key]
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def init_state() -> None:
    if st.session_state.get("_state_version") != STATE_VERSION:
        for key in _DEFAULTS:
            st.session_state[key] = _default(key)
        st.session_state["_state_version"] = STATE_VERSION
    else:
        for key in _DEFAULTS:
            if key not in st.session_state:
                st.session_state[key] = _default(key)


def reset_game_state() -> None:
    """Clear all game-specific state when switching to a new game."""
    game_keys = [
        "current_drives", "evaluated_drives", "drive_qcs",
        "system_results", "drive_snapshots", "stat_corrections",
        "alert_log", "warning_message", "warning_type", "alert_shown_until",
        "rate_limit_skip_remaining",
        # Corrections filters: a stale team abbrev from the previous game would
        # hide everything in the new one.
        "corr_impact_filter", "corr_team_filter", "corr_field_filter",
        "corr_play_filter",
    ]
    for key in game_keys:
        st.session_state[key] = _default(key)


def set_system_result(drive_id: str, market: str, value: str) -> None:
    """Store a single system result value entered by a trader."""
    if drive_id not in st.session_state.system_results:
        st.session_state.system_results[drive_id] = {}
    st.session_state.system_results[drive_id][market] = value


def get_system_result(drive_id: str, market: str) -> str:
    return st.session_state.system_results.get(drive_id, {}).get(market, "")


def clear_system_results(drive_id: str) -> None:
    st.session_state.system_results.pop(drive_id, None)
