from __future__ import annotations

NFL_TEAM_COLORS: dict[str, str] = {
    "ARI": "#97233F", "ATL": "#A71930", "BAL": "#241773", "BUF": "#00338D",
    "CAR": "#0085CA", "CHI": "#0B162A", "CIN": "#FB4F14", "CLE": "#311D00",
    "DAL": "#003594", "DEN": "#002244", "DET": "#0076B6", "GB":  "#203731",
    "HOU": "#03202F", "IND": "#002C5F", "JAX": "#006778", "KC":  "#E31837",
    "LAC": "#0080C6", "LAR": "#003594", "LV":  "#A5ACAF", "MIA": "#008E97",
    "MIN": "#4F2683", "NE":  "#002244", "NO":  "#D3BC8D", "NYG": "#0B2265",
    "NYJ": "#125740", "PHI": "#004C54", "PIT": "#FFB612", "SF":  "#AA0000",
    "SEA": "#002244", "TB":  "#D50A0A", "TEN": "#0C2340", "WAS": "#5A1414",
}

NFL_TEAM_ALT_COLORS: dict[str, str] = {
    "ARI": "#FFB612", "ATL": "#000000", "BAL": "#9E7C0C", "BUF": "#C60C30",
    "CAR": "#101820", "CHI": "#C83803", "CIN": "#000000", "CLE": "#FF3C00",
    "DAL": "#869397", "DEN": "#FB4F14", "DET": "#B0B7BC", "GB":  "#FFB612",
    "HOU": "#03202F", "IND": "#A2AAAD", "JAX": "#D7A22A", "KC":  "#FFB81C",
    "LAC": "#FFC20E", "LAR": "#FFA300", "LV":  "#000000", "MIA": "#FC4C02",
    "MIN": "#FFC62F", "NE":  "#C60C30", "NO":  "#101820", "NYG": "#A71930",
    "NYJ": "#FFFFFF", "PHI": "#A5ACAF", "PIT": "#000000", "SF":  "#B3995D",
    "SEA": "#69BE28", "TB":  "#FF7900", "TEN": "#4B92DB", "WAS": "#FFB612",
}

_COLOR_DISTANCE_THRESHOLD = 100


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def color_distance(a: str, b: str) -> float:
    r1, g1, b1 = _hex_to_rgb(a)
    r2, g2, b2 = _hex_to_rgb(b)
    return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5


def pill_text_color(bg_hex: str) -> str:
    h = bg_hex.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.5 else "#ffffff"


def resolve_team_colors(
    home_abbrev: str,
    away_abbrev: str,
    fallback: dict[str, tuple[str, str]] | None = None,
) -> dict[str, str]:
    """Resolve pill colors for two teams.

    NFL teams use the curated NFL_TEAM_COLORS dict. For any abbreviation not in
    that dict (e.g. all CFB teams), `fallback` supplies (primary, alternate)
    colors — pass the ESPN-provided team colors here. Falls back to grey only
    when nothing is available.
    """
    fallback = fallback or {}

    def _primary(abbrev: str) -> str:
        if abbrev in NFL_TEAM_COLORS:
            return NFL_TEAM_COLORS[abbrev]
        fb = fallback.get(abbrev)
        return fb[0] if fb and fb[0] else "#888888"

    def _alternate(abbrev: str) -> str:
        if abbrev in NFL_TEAM_ALT_COLORS:
            return NFL_TEAM_ALT_COLORS[abbrev]
        fb = fallback.get(abbrev)
        return fb[1] if fb and fb[1] else _primary(abbrev)

    home_color = _primary(home_abbrev)
    away_color = _primary(away_abbrev)
    # If the two primaries are too similar, swap the away team to its alternate.
    if color_distance(home_color, away_color) < _COLOR_DISTANCE_THRESHOLD:
        away_color = _alternate(away_abbrev)
    return {home_abbrev: home_color, away_abbrev: away_color}


def _is_valid_hex(color: str) -> bool:
    h = (color or "").lstrip("#")
    if len(h) != 6:
        return False
    try:
        int(h, 16)
        return True
    except ValueError:
        return False


def team_fallback_colors(*teams) -> dict[str, tuple[str, str]]:
    """Build a {abbrev: (primary, alternate)} fallback map from Team objects,
    using their ESPN-provided colors. Skips any malformed/empty color so
    resolve_team_colors falls through to grey rather than crashing."""
    out: dict[str, tuple[str, str]] = {}
    for team in teams:
        if not team or not team.abbreviation:
            continue
        primary = team.color if _is_valid_hex(team.color) else ""
        alt = team.alternate_color if _is_valid_hex(team.alternate_color) else ""
        out[team.abbreviation] = (primary, alt)
    return out


def team_color(abbrev: str, color_map: dict[str, str] | None = None) -> str:
    if color_map and abbrev in color_map:
        return color_map[abbrev]
    return NFL_TEAM_COLORS.get(abbrev, "#888888")
