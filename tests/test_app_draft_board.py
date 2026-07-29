"""Draft Board sort-regression guard for the rebuilt tab (2026-07-22). Imports
draft_board_2026 directly and never renders the entrypoint. For every one of the 10 sortable
columns, ascending AND descending order must be numerically correct (never a string sort), and
every sentinel row — a rookie QB with no projection (NaN gap/rank/proj) or a player with no
talent score — must land at the BOTTOM in BOTH directions (na_position='last').
"""
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parents[1]


def test_board_sort_is_numeric_and_sentinels_sink():
    sys.path.insert(0, str(_HERE))
    import draft_board_2026 as board

    df = board._load_board_2026()
    assert list(board.SORT_KEYS)[0] == "Sleeper ADP", "default sort column must be Sleeper ADP"
    assert len(board.SORT_KEYS) == 10, \
        "expected 10 sortable columns (2026-07-22 projection-table rebuild)"

    for label, key in board.SORT_KEYS.items():
        for asc in (True, False):
            v = board._sort_board(df, label, ascending=asc)
            k = pd.to_numeric(v[key], errors="coerce").to_numpy()
            isna = pd.isna(k)
            n_sent = int(isna.sum())
            # sentinels (NaN key) form the trailing block, in BOTH directions
            if n_sent:
                assert isna[len(k) - n_sent:].all() and not isna[:len(k) - n_sent].any(), \
                    f"{label} asc={asc}: sentinel rows not all pinned to the bottom"
            # non-sentinel keys strictly ordered by the numeric value (not the string)
            real = k[~isna]
            if len(real) > 1:
                if asc:
                    assert (real[:-1] <= real[1:]).all(), \
                        f"{label} ascending is not numerically ordered (string sort?)"
                else:
                    assert (real[:-1] >= real[1:]).all(), \
                        f"{label} descending is not numerically ordered (string sort?)"

    # rookie QBs (no Model Proj) sink last on Model Gap / Model Proj, both ways
    for asc in (True, False):
        for label in ("Model Gap", "Model Proj", "Sleeper Gap", "Sleeper Proj"):
            g = board._sort_board(df, label, ascending=asc)
            assert pd.isna(pd.to_numeric(g[board.SORT_KEYS[label]], errors="coerce").iloc[-1]), \
                f"a no-data row must be last on {label} sort (asc={asc})"

    print(f"OK  board sort: {len(board.SORT_KEYS)} columns numeric asc+desc; "
          f"no-data rows sink to bottom both ways; default Sleeper-ADP")


def test_outside_market_sort_is_numeric_and_blanks_sink():
    """Same guarantee for the outside-market explorer: every numeric sort orders on the
    number (never the display string) and blank talent cells stay at the BOTTOM in both
    directions. The default is Model Proj, and the render pass opens it descending."""
    sys.path.insert(0, str(_HERE))
    import draft_board_2026 as board

    outside = board._load_outside_market_players()
    assert list(board.OUTSIDE_SORT_KEYS)[0] == "Model Proj", \
        "the default outside-market sort column must be Model Proj"
    for required in ("Model Proj", "Model Proj Position Rank", "NFL Talent",
                     "College Talent", "Player"):
        assert required in board.OUTSIDE_SORT_KEYS, f"missing sort option: {required}"
    # No price or gap column may be sortable here — none exists for these players.
    assert not {"adp_half_ppr", "sleeper_proj", "pos_rank", "sleeper_gap", "model_gap"} \
        & set(board.OUTSIDE_SORT_KEYS.values())

    numeric_keys = {"model_proj", "model_proj_pos_rank_full", "nfl_talent", "college_talent"}
    blanks_seen = set()
    for label, key in board.OUTSIDE_SORT_KEYS.items():
        assert key in outside.columns, f"sort key {key!r} for {label!r} is missing"
        for asc in (True, False):
            ordered = board._sort_outside_market(outside, label, ascending=asc)
            assert len(ordered) == len(outside), f"{label}: rows lost in the sort"
            if key not in numeric_keys:
                continue
            values = pd.to_numeric(ordered[key], errors="coerce").to_numpy()
            isna = pd.isna(values)
            n_blank = int(isna.sum())
            if n_blank:
                blanks_seen.add(key)
                assert isna[len(values) - n_blank:].all() \
                    and not isna[:len(values) - n_blank].any(), \
                    f"{label} asc={asc}: blank cells not pinned to the bottom"
            real = values[~isna]
            if len(real) > 1:
                if asc:
                    assert (real[:-1] <= real[1:]).all(), \
                        f"{label} ascending is not numerically ordered (string sort?)"
                else:
                    assert (real[:-1] >= real[1:]).all(), \
                        f"{label} descending is not numerically ordered (string sort?)"

    # The nulls-last guarantee must actually be exercised, not vacuously true.
    assert {"nfl_talent", "college_talent"} <= blanks_seen, \
        f"expected blank talent cells to exercise the sort, saw {blanks_seen}"
    # Model Proj is complete here by construction, so it has nothing to sink.
    assert outside["model_proj"].notna().all()

    print(f"OK  outside-market sort: {len(board.OUTSIDE_SORT_KEYS)} options, numeric asc+desc, "
          f"blank talent cells sink both ways; default Model Proj on {len(outside)} rows")


if __name__ == "__main__":
    test_board_sort_is_numeric_and_sentinels_sink()
    test_outside_market_sort_is_numeric_and_blanks_sink()
