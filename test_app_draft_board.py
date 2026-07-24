"""Draft Board sort-regression guard for the rebuilt tab (2026-07-22). Imports
draft_board_2026 directly and never renders the entrypoint. For every one of the 10 sortable
columns, ascending AND descending order must be numerically correct (never a string sort), and
every sentinel row — a rookie QB with no projection (NaN gap/rank/proj) or a player with no
talent score — must land at the BOTTOM in BOTH directions (na_position='last').
"""
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent


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


if __name__ == "__main__":
    test_board_sort_is_numeric_and_sentinels_sink()
