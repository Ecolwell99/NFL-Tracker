from __future__ import annotations
import streamlit as st
from qc.corrections import (
    StatCorrection, PLAY_CLASS_RUSH, PLAY_CLASS_PASS,
)

# Filter option constants. Kept as module-level strings so the session-state
# values are stable — see the tab-navigation note in app.py for why a filter's
# stored value must never be a string that can stop existing.
_IMPACT_ALL    = "All"
_IMPACT_MARKET = "Market Impacted"
_IMPACT_NONE   = "No Impact"

_ANY = "All"

# Every value StatCorrection.field can hold, in the order they appear in
# qc/corrections.py. Fixed list rather than derived, so the dropdown does not
# reshuffle as corrections arrive mid-game.
_FIELD_FILTERS = [
    "Drive Result",
    "Furthest Advance",
    "Play Type",
    "Play Yards",
    "Scoring Play Flag",
    "Players Involved",
    "Play Removed",
]

_PLAY_CLASS_FILTERS = [PLAY_CLASS_RUSH, PLAY_CLASS_PASS]

# Drive-level corrections carry no play class. The user chose to HIDE these when
# filtering to Rush/Pass, which means a Furthest Advance card (the yardline
# crossing audit trail) can be filtered out of view — so the tab says so
# explicitly rather than letting it disappear silently.
_DRIVE_LEVEL_FIELDS = frozenset({"Drive Result", "Furthest Advance"})


def _init_filter_state() -> None:
    defaults = {
        "corr_impact_filter": _IMPACT_ALL,
        "corr_team_filter":   _ANY,
        "corr_field_filter":  _ANY,
        "corr_play_filter":   _ANY,
        "corr_market_filter": _ANY,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _set(key: str, value: str) -> None:
    """on_click setter — avoids the double-click bug seen on the Drives tab."""
    st.session_state[key] = value


def render(
    corrections: list[StatCorrection],
    color_mode: bool = True,
    game_home_abbrev: str = "",
    game_away_abbrev: str = "",
) -> None:
    _init_filter_state()

    # Empty state for "genuinely nothing happened" — this is the ONLY green
    # all-clear. The filtered-to-zero case further down must never render green.
    #
    # The filter row renders ABOVE it and is deliberately NOT behind this early
    # return: a trader watching a game that has not yet produced a correction
    # should be able to preset Play=Rush at kickoff, and hiding the controls
    # entirely also made the feature look undeployed.
    if not corrections:
        _render_filter_row(corrections, game_home_abbrev, game_away_abbrev)
        st.markdown(
            '<div style="padding:24px; text-align:center; background:#132117; '
            'border-radius:10px; color:#66ff99; font-size:20px; font-weight:700; '
            'margin-top:16px;">'
            '✓ No stat corrections detected</div>',
            unsafe_allow_html=True,
        )
        return

    # Banner counts ALL corrections, never the filtered subset. A filter set in
    # Q1 must not be able to hide the fact that a Q4 correction exists.
    total = len(corrections)
    st.markdown(
        f'<div style="padding:12px 16px; background:#3a1600; border-radius:8px; '
        f'color:#ffd966; font-weight:700; font-size:16px; margin-bottom:16px;">'
        f'⚠ {total} stat correction{"s" if total != 1 else ""} detected'
        f'</div>',
        unsafe_allow_html=True,
    )

    _render_filter_row(corrections, game_home_abbrev, game_away_abbrev)

    visible = _apply_filters(corrections)

    _render_result_count(len(visible), total)

    # A Rush/Pass filter hides drive-level cards, including Furthest Advance —
    # the yardline-crossing audit trail. Say so, so a missing crossing card is
    # never mistaken for "no crossing happened".
    hidden_drive_level = _hidden_drive_level_count(corrections)
    if hidden_drive_level:
        st.markdown(
            f'<div style="padding:8px 12px; background:#2a2a00; border-radius:6px; '
            f'color:#ffd966; font-size:12px; margin-bottom:10px;">'
            f'{hidden_drive_level} drive-level correction'
            f'{"s" if hidden_drive_level != 1 else ""} '
            f'(Drive Result / Furthest Advance) hidden by the '
            f'{st.session_state.corr_play_filter} filter — set Play back to All to see '
            f'{"them" if hidden_drive_level != 1 else "it"}.'
            f'</div>',
            unsafe_allow_html=True,
        )

    if not visible:
        # Deliberately NOT green. An all-clear here would read as "this game is
        # clean" on a game that has `total` corrections sitting behind a filter.
        st.markdown(
            '<div style="padding:20px; text-align:center; '
            'background:var(--secondary-background-color); border-radius:10px; '
            'opacity:0.7; font-size:15px; font-weight:600; margin-top:8px;">'
            'No corrections match this filter</div>',
            unsafe_allow_html=True,
        )
        return

    for c in reversed(visible):
        _render_correction_card(c)


# ------------------------------------------------------------------ #
# Filter UI
# ------------------------------------------------------------------ #

def _render_filter_row(
    corrections: list[StatCorrection],
    home_abbrev: str,
    away_abbrev: str,
) -> None:
    # Impact — button row, mirrors the Drives tab team filter.
    #
    # Guard against a stored value that is no longer one of the three options —
    # e.g. a session still holding the old "Market-Moving" label after it was
    # renamed to "Market Impacted". Without this no button reads as selected and
    # the filter matches nothing, silently hiding every card.
    if st.session_state.corr_impact_filter not in (_IMPACT_ALL, _IMPACT_MARKET, _IMPACT_NONE):
        st.session_state.corr_impact_filter = _IMPACT_ALL

    cols = st.columns([1, 1, 1, 3])
    for col, label in zip(cols, (_IMPACT_ALL, _IMPACT_MARKET, _IMPACT_NONE)):
        with col:
            st.button(
                label,
                use_container_width=True,
                key=f"corr_impact_btn_{label}",
                type="primary" if st.session_state.corr_impact_filter == label else "secondary",
                on_click=_set,
                args=("corr_impact_filter", label),
            )

    # Team / Type / Play / Market — selectboxes.
    team_options = [_ANY] + [a for a in (away_abbrev, home_abbrev) if a]

    # Market options are built FROM the corrections present, not from a hardcoded
    # market list: Sack This Drive, Punt Fair Catch and 4th Down Conversion can
    # never produce a correction, so a static list would show dead options that
    # always return nothing.
    markets_present = sorted({m for c in corrections for m in c.markets_impacted})
    market_options = [_ANY] + markets_present

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _selectbox("Team", "corr_team_filter", team_options)
    with c2:
        _selectbox("Type", "corr_field_filter", [_ANY] + _FIELD_FILTERS)
    with c3:
        _selectbox("Play", "corr_play_filter", [_ANY] + _PLAY_CLASS_FILTERS)
    with c4:
        _selectbox("Market", "corr_market_filter", market_options)


def _selectbox(prefix: str, state_key: str, options: list[str]) -> None:
    """
    Selectbox bound to session state. Guards against a stored value that is no
    longer in options (e.g. a Market filter set on a market that has since been
    cleared by reset_game_state) by falling back to All instead of raising.
    """
    if st.session_state[state_key] not in options:
        st.session_state[state_key] = _ANY
    st.selectbox(
        prefix,
        options=options,
        format_func=lambda v: f"{prefix}: {v}",
        key=state_key,
        label_visibility="collapsed",
    )


def _render_result_count(shown: int, total: int) -> None:
    if shown == total:
        text = f"Showing all {total}"
    else:
        text = f"Showing {shown} of {total} corrections"
    st.markdown(
        f'<div style="font-size:12px; opacity:0.55; margin:6px 0 10px 0;">{text}</div>',
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------ #
# Filtering
# ------------------------------------------------------------------ #

def _apply_filters(
    corrections: list[StatCorrection],
    ignore_play_filter: bool = False,
) -> list[StatCorrection]:
    impact = st.session_state.corr_impact_filter
    team   = st.session_state.corr_team_filter
    field  = st.session_state.corr_field_filter
    play   = st.session_state.corr_play_filter
    market = st.session_state.corr_market_filter

    out = []
    for c in corrections:
        if impact == _IMPACT_MARKET and not c.markets_impacted:
            continue
        if impact == _IMPACT_NONE and c.markets_impacted:
            continue
        # getattr keeps old corrections from a pre-upgrade session log renderable
        # instead of crashing on a missing attribute.
        if team != _ANY and getattr(c, "team_abbrev", "") != team:
            continue
        if field != _ANY and c.field != field:
            continue
        if not ignore_play_filter and play != _ANY \
                and play not in getattr(c, "play_classes", []):
            continue
        if market != _ANY and market not in c.markets_impacted:
            continue
        out.append(c)
    return out


def _hidden_drive_level_count(corrections: list[StatCorrection]) -> int:
    """
    How many drive-level cards the active Rush/Pass filter is hiding — counted
    against the OTHER filters, so a card already excluded by Team or Market is
    not blamed on the Play filter and double-reported.
    """
    if st.session_state.corr_play_filter == _ANY:
        return 0
    return sum(
        1 for c in _apply_filters(corrections, ignore_play_filter=True)
        if c.field in _DRIVE_LEVEL_FIELDS
    )


# ------------------------------------------------------------------ #
# Cards
# ------------------------------------------------------------------ #

def _render_correction_card(c: StatCorrection) -> None:
    markets_str = ", ".join(c.markets_impacted) if c.markets_impacted else "None"
    play_str = (
        f'<div style="font-size:11px; opacity:0.6; margin-top:4px; font-style:italic;">'
        f'{c.play_description}</div>'
        if c.play_description else ""
    )
    team = getattr(c, "team_abbrev", "")
    team_str = (
        f'<span style="font-size:11px; opacity:0.5; margin-left:8px;">{team}</span>'
        if team else ""
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
                    {team_str}
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
