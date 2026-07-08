"""Ported directly from the NHL tool."""
from __future__ import annotations
import streamlit as st

_STYLES = {
    "alert": "background-color:#3a1600; color:#ffd966; border:2px solid #ff9900",
    "ok":    "background-color:#132117; color:#66ff99; border:2px solid #2e6b45",
    "info":  "background-color:#0d1f3c; color:#66aaff; border:2px solid #2255aa",
}


def warning_box(message: str, warning_type: str = "ok") -> None:
    style = _STYLES.get(warning_type, _STYLES["ok"])
    st.markdown(
        f'<div style="margin-top:10px; margin-bottom:18px; padding:16px; border-radius:10px;'
        f' font-size:22px; font-weight:700; {style}">{message}</div>',
        unsafe_allow_html=True,
    )
