from __future__ import annotations
import streamlit as st
from services.espn_provider import ESPNProvider, RateLimitedError
from models.game import Game
from models.drive import Drive, SpecialTeamsScore

_provider = ESPNProvider()


@st.cache_data(ttl=30, show_spinner=False)
def cached_get_games() -> list[Game]:
    return _provider.get_games()


@st.cache_data(ttl=3, show_spinner=False)
def cached_get_drives(game_id: str) -> list[Drive]:
    return _provider.get_drives(game_id)


@st.cache_data(ttl=3, show_spinner=False)
def cached_get_special_teams_scores(game_id: str) -> list[SpecialTeamsScore]:
    return _provider.get_special_teams_scores(game_id)


@st.cache_data(ttl=5, show_spinner=False)
def cached_get_game(game_id: str) -> Game:
    return _provider.get_game(game_id)


@st.cache_data(ttl=5, show_spinner=False)
def cached_get_boxscore(game_id: str) -> dict:
    return _provider.get_boxscore(game_id)
