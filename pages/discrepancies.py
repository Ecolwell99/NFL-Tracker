from __future__ import annotations
import streamlit as st
from qc.comparator import DriveQC, QCResult
from qc.status import QCStatus
from components.tables import render_table


def render(drive_qcs: list[DriveQC], color_mode: bool = True) -> None:
    mismatches = [
        (qc, r)
        for qc in drive_qcs
        for r in qc.results
        if r.status == QCStatus.MISMATCH
    ]

    if not mismatches:
        st.markdown(
            '<div style="padding:24px; text-align:center; background:#132117; '
            'border-radius:10px; color:#66ff99; font-size:20px; font-weight:700;">'
            '✓ No discrepancies detected</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div style="padding:12px 16px; background:#3a1600; border-radius:8px; '
        f'color:#ffd966; font-weight:700; font-size:16px; margin-bottom:16px;">'
        f'⚠ {len(mismatches)} discrepanc{"ies" if len(mismatches) != 1 else "y"} found'
        f'</div>',
        unsafe_allow_html=True,
    )

    rows = []
    for qc, result in mismatches:
        rows.append({
            "Drive":    qc.drive_label,
            "Team":     qc.team_abbrev,
            "Market":   result.market,
            "Expected": result.expected,
            "System":   result.system,
            "Note":     result.note,
        })

    render_table(rows, color_mode=False)
