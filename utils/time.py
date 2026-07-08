from __future__ import annotations


def parse_clock_to_seconds(clock_str: str) -> int | None:
    try:
        parts = clock_str.strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, AttributeError):
        pass
    return None


def seconds_to_clock(total_seconds: int) -> str:
    total_seconds = max(0, total_seconds)
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def format_possession_time(seconds: int) -> str:
    return seconds_to_clock(seconds)


def period_label(period: int) -> str:
    labels = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}
    if period in labels:
        return labels[period]
    return f"OT{period - 4}" if period > 4 else f"Q{period}"
