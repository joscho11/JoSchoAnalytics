"""SHARED exact drive-result definitions. Single source of truth for all three panel builders.

`str.contains("Touchdown")` also matches **'Opp touchdown'** -- a defensive or return score BY THE
OPPONENT -- and credited the offense +7 for being scored on, while also counting it as a red-zone
touchdown. The fix existed in `build_segment_offense.py` from v3.3 but was never propagated:
`build_team_offense_panel.py` and `build_allocation_panel.py` still carried the substring test.

Having one corrected copy and two broken copies is exactly why this now lives in ONE module that
all three builders import.

Measured on 2014/2018/2022/2025 REG drives: **611** 'Opp touchdown' drives were being credited to
the offense as touchdowns.
"""

# Exact mapping from `fixed_drive_result` to offensive points. No substring matching, ever.
DRIVE_POINTS = {
    "Touchdown": 7.0,            # the ONLY offensive touchdown category
    "Field goal": 3.0,
    "Safety": -2.0,
    "Opp touchdown": 0.0,        # opponent scored -- offense credited NOTHING
    "Punt": 0.0,
    "Turnover": 0.0,
    "Turnover on downs": 0.0,
    "Missed field goal": 0.0,
    "End of half": 0.0,
    "End of game": 0.0,
}

OFFENSIVE_TD = "Touchdown"       # red-zone TD rate uses this and nothing else


def drive_points(result_series):
    """Offensive points per drive. Raises on any unmapped category rather than silently zeroing."""
    assert_known_categories(result_series)
    return result_series.map(DRIVE_POINTS)


def is_offensive_td(result_series):
    """Exact equality. Never `.str.contains`."""
    return result_series.eq(OFFENSIVE_TD)


def assert_known_categories(result_series):
    """An unmapped category is a data change, not a zero. Fail loudly."""
    seen = set(result_series.dropna().unique())
    unknown = seen - set(DRIVE_POINTS)
    assert not unknown, (
        f"unmapped fixed_drive_result categories {sorted(unknown)} -- classify them explicitly in "
        f"drive_definitions.DRIVE_POINTS rather than letting them fall through as 0 points")
    return True


# Canonical proxy names (ratified v3.3, propagated v3.8). A flat TD=7 assumes the extra point and
# ignores 2-point attempts and missed XPs, and the measure excludes all defensive and
# special-teams scoring -- so these are PROXIES and must never be called literal offensive points.
PPD_PROXY = "drive_scoring_points_per_drive_proxy"
PPG_PROXY = "drive_scoring_points_per_game_proxy"
PRIOR_PPD_PROXY = "prior_drive_scoring_points_per_drive_proxy"

# Names retired from the live pipeline. Permitted only in labelled superseded artifacts.
RETIRED_NAMES = {
    "points_per_drive": PPD_PROXY,
    "off_points_per_game": PPG_PROXY,
    "prior_points_per_drive": PRIOR_PPD_PROXY,
}
