from __future__ import annotations
import streamlit as st
from qc.corrections import StatCorrection


def render(corrections: list[StatCorrection], color_mode: bool = True) -> None:
    if not corrections:
        st.markdown(
            '<div style="padding:24px; text-align:center; background:#132117; '
            'border-radius:10px; color:#66ff99; font-size:20px; font-weight:700;">'
            '✓ No stat corrections detected</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div style="padding:12px 16px; background:#3a1600; border-radius:8px; '
        f'color:#ffd966; font-weight:700; font-size:16px; margin-bottom:16px;">'
        f'⚠ {len(corrections)} stat correction{"s" if len(corrections) != 1 else ""} detected'
        f'</div>',
        unsafe_allow_html=True,
    )

    for c in reversed(corrections):
        _render_correction_card(c)


def _render_correction_card(c: StatCorrection) -> None:
    markets_str = ", ".join(c.markets_impacted) if c.markets_impacted else "None"
    play_str = (
        f'<div style="font-size:11px; opacity:0.6; margin-top:4px; font-style:italic;">'
        f'{c.play_description}</div>'
        if c.play_description else ""
    )

    st.markdown(
        f"""
        <div style="background:var(--secondary-background-color); border-radius:8px;
                    padding:12px 16px; margin-bottom:8px;
                    border-left:4px solid #ff9900;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                    <span style="font-weight:800; font-size:14px;">{c.drive_label}</span>
                    <span style="margin-left:10px; font-size:13px; opacity:0.7;">
                        {c.field}
                    </span>
                </div>
                <span style="font-size:11px; opacity:0.5;">{c.detected_at}</span>
            </div>
            <div style="margin-top:6px; font-size:13px;">
                <span style="background:#cc2200; color:#fff; padding:1px 8px;
                             border-radius:4px; font-size:12px;">{c.previous_value}</span>
                <span style="margin:0 8px; opacity:0.6;">→</span>
                <span style="background:#00cc44; color:#000; padding:1px 8px;
                             border-radius:4px; font-size:12px;">{c.new_value}</span>
            </div>
            {play_str}
            <div style="margin-top:6px; font-size:11px; opacity:0.55;">
                Markets impacted: {markets_str}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
