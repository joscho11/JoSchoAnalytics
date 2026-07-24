"""Dependency-free shared schedule settings for the seasonal board and dashboard."""
import os
from datetime import date


# Kickoff-week default: the scheduled pre-draft ADP refresh pauses on or after this date.
SEASON_START = date(2026, 9, 4)


def board_refresh_season_start() -> date:
    """Return the environment override when present, else the shared kickoff default."""
    raw = os.environ.get("BOARD_REFRESH_SEASON_START")
    return date.fromisoformat(raw) if raw else SEASON_START
