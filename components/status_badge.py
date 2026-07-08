from __future__ import annotations
import streamlit as st
from qc.status import QCStatus, QC_STATUS_COLOR, QC_STATUS_TEXT_COLOR
from utils.colors import pill_text_color


def status_badge_html(status: QCStatus) -> str:
    bg = QC_STATUS_COLOR[status]
    fg = QC_STATUS_TEXT_COLOR[status]
    return (
        f'<span style="background-color:{bg}; color:{fg}; padding:3px 12px; '
        f'border-radius:12px; font-weight:700; font-size:12px;">'
        f'{status.value}</span>'
    )


def mismatch_count_html(count: int) -> str:
    if count == 0:
        return (
            '<span style="background-color:#00cc44; color:#000; padding:3px 10px; '
            'border-radius:12px; font-weight:700; font-size:12px;">✓ Clean</span>'
        )
    return (
        f'<span style="background-color:#cc2200; color:#fff; padding:3px 10px; '
        f'border-radius:12px; font-weight:700; font-size:12px;">'
        f'⚠ {count} mismatch{"es" if count != 1 else ""}</span>'
    )
