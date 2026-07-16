"""Draft Board sort-regression guard (survives the multipage swap — it imports
draft_board_2026 directly and never renders the entrypoint). The former tab-render
test (test_draft_value_2026_tab_renders_and_filters) was retired when the tab monolith
was removed in Batch 3e; the board's rendered behaviour is now covered by
test_board_page.py against the st.table page.
"""
import sys
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent


def test_board_sort_is_numeric_and_sentinels_sink():
    """Regression guard against the recurring string-sort bug (see
    audit/board_sort_diagnosis_2026-07-13.md). For every one of the 9 sortable
    columns, ascending AND descending order must be numerically correct, and every
    sentinel row — Gainwell's blank Gap/Proj rank, and all 'Rookie' and all '–'
    efficiency rows — must land at the BOTTOM in BOTH directions. Fails if any column
    reverts to string sorting or a sentinel floats to the top."""
    sys.path.insert(0, str(_HERE))
    import draft_board_2026 as board

    df = board._load_board_2026()
    assert list(board.SORT_KEYS)[0] == "Gap", "default sort column must be Gap"
    assert len(board.SORT_KEYS) == 11, \
        "expected 11 sortable columns (9 + Talent Score + Rookie Score, 2026-07-16)"

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
            if asc:
                assert (real[:-1] <= real[1:]).all(), \
                    f"{label} ascending is not numerically ordered (string sort?)"
            else:
                assert (real[:-1] >= real[1:]).all(), \
                    f"{label} descending is not numerically ordered (string sort?)"

    # column-specific sentinel identity: Gainwell (blank Gap) last on Gap, both ways
    for asc in (True, False):
        g = board._sort_board(df, "Gap", ascending=asc)
        assert pd.isna(g["value_gap"].iloc[-1]), \
            f"Gainwell (blank Gap) must be last on Gap sort (asc={asc})"
        p = board._sort_board(df, "Proj position rank", ascending=asc)
        assert pd.isna(p["proj_pos_rank"].iloc[-1]), \
            f"blank Proj-rank row must be last on Proj-rank sort (asc={asc})"
        # every 'Rookie' and every '–' efficiency row sits in the bottom block
        e = board._sort_board(df, "NFL Efficiency %ile (pos)", ascending=asc)
        n_rk = int((df["eff_disp"] == "Rookie").sum())
        n_dash = int((df["eff_disp"] == "–").sum())
        tail = set(e["eff_disp"].iloc[-(n_rk + n_dash):])
        assert tail <= {"Rookie", "–"}, \
            f"Efficiency sort (asc={asc}): a real value floated into the sentinel block"

    print(f"OK  board sort: 9 columns numeric asc+desc; sentinels "
          f"(Gainwell, {int((df['eff_disp']=='Rookie').sum())} Rookie, "
          f"{int((df['eff_disp']=='–').sum())} '–') sink to bottom both ways; default Gap-desc")


if __name__ == "__main__":
    test_board_sort_is_numeric_and_sentinels_sink()
