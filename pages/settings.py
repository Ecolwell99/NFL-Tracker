from __future__ import annotations
import streamlit as st


def render() -> None:
    st.markdown("### Settings")

    st.markdown("**Refresh**")
    interval = st.slider(
        "Auto-refresh interval (seconds)",
        min_value=3, max_value=60,
        value=st.session_state.get("refresh_interval_ms", 5000) // 1000,
        step=1,
    )
    st.session_state["refresh_interval_ms"] = interval * 1000

    st.divider()
    st.markdown("**Display**")

    col1, col2 = st.columns(2)
    with col1:
        st.session_state["color_mode"] = st.toggle(
            "Color mode", value=st.session_state.get("color_mode", True)
        )
        st.session_state["filter_recent"] = st.toggle(
            "Newest first", value=st.session_state.get("filter_recent", False)
        )
    with col2:
        st.session_state["show_void_drives"] = st.toggle(
            "Show void drives (End of Half)",
            value=st.session_state.get("show_void_drives", True),
        )
        st.session_state["show_nfl_only_markets"] = st.toggle(
            "Show NFL-only markets",
            value=st.session_state.get("show_nfl_only_markets", True),
        )

    st.divider()
    st.markdown("**Data**")
    if st.button("Clear stat corrections log", type="secondary"):
        st.session_state["stat_corrections"] = []
        st.success("Corrections log cleared.")

    if st.button("Reset all system results", type="secondary"):
        st.session_state["system_results"] = {}
        st.success("System results cleared.")
