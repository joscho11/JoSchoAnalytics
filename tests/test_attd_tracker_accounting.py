import pandas as pd

from site_pages.attd_tracker import _max_drawdown


def test_max_drawdown_uses_cumulative_season_week_equity_from_zero():
    frame = pd.DataFrame({
        "season": [2026, 2026, 2026, 2026],
        "week": [3, 1, 2, 2],
        "_settled": [True] * 4,
        "_profit_units": [-60.0, -12.0, 5.0, 7.0],
    })

    # Chronological weekly profit is -12, +12, -60. The low-water mark is
    # cumulative equity -60 from a starting balance of zero.
    assert _max_drawdown(frame) == -60.0


def test_max_drawdown_does_not_count_unsettled_rows():
    frame = pd.DataFrame({
        "season": [2026, 2026],
        "week": [1, 2],
        "_settled": [True, False],
        "_profit_units": [-2.0, -100.0],
    })
    assert _max_drawdown(frame) == -2.0
