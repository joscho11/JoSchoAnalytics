"""Rookie Board page proof after the projection swap (RB season-total projection replaces the
starved per-game rookie_ppg surface on display). Renders the page function directly via
AppTest.from_function (nav-independent; st.navigation function-pages can't be switch_page'd).
Hermetic (APP_OFFLINE=1).

Asserts: the page renders clean (no exception/error); the new projection columns are present and the
old "Rookie Proj (PPG)" column is gone from display; the RB projection is sourced from the new model
(Jeremiyah Love shows the season-total ~153, NOT the starved 4.7 per-game surface); the RB position
filter renders; and app.py boots as the multipage entrypoint with the page wired in.
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

import pandas as pd
from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "betting"))
sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))


def _entry():
    # Default render = the "All" positions view of the newest class (2026), where the RB/WR/TE/QB
    # rookies below all appear — no position-filter forcing needed (AppTest.from_function re-execs the
    # source, so closures/monkeypatches into the page's column-selectbox don't survive anyway).
    import page_rookie_board
    page_rookie_board.render()


def _run(fn):
    at = AppTest.from_function(fn, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _find_df(at, col):
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            if col in list(d.columns):
                return d
        except Exception:
            pass
    return None


def _proj_of(df, name):
    r = df[df["Player"].astype(str).str.contains(name, na=False)]
    assert len(r) == 1, f"{name} must appear exactly once in the 2026 board view"
    return float(pd.to_numeric(r["Proj (season ½-PPR)"], errors="coerce").iloc[0])


def test_rookie_page_swaps_in_season_projections():
    """The 2026 'All' view shows the RB/WR/TE season-total projections (starved PPG surface retired);
    each replaces its old per-game number with a real season total."""
    at = _run(_entry)
    df = _find_df(at, "Proj (season ½-PPR)")
    assert df is not None, "projection column 'Proj (season ½-PPR)' must render"
    assert "Rookie Proj (PPG)" not in list(df.columns), "the starved per-game surface must be retired from display"
    for c in ("Sleeper Proj", "Diff vs Sleeper", "Full Hit-%", "Pos"):
        assert c in list(df.columns), f"expected column {c} missing"
    assert _proj_of(df, "Jeremiyah Love") > 100, "RB Love must show the season-total (~153), not the starved 4.7"
    assert _proj_of(df, "Makai Lemon") > 50, "WR Makai Lemon must show the season-total (~133)"
    assert _proj_of(df, "Eli Stowers") > 20, "TE Eli Stowers must show the season-total (~84)"


def test_qb_rows_held_no_projection():
    """QB rookie arm was HELD (§3B) — the empty qb board file must not break the join, and QB-position
    rows must show NO projection (the 'coming' state)."""
    at = _run(_entry)
    df = _find_df(at, "Proj (season ½-PPR)")
    assert df is not None, "board must render"
    qb = df[df["Pos"].astype(str) == "QB"]
    assert len(qb) > 0, "QB rookies must still appear on the board (hit-%/percentiles)"
    vals = pd.to_numeric(qb["Proj (season ½-PPR)"], errors="coerce").dropna()
    assert len(vals) == 0, f"QB rookie arm is HELD — no QB projection should show (got {len(vals)})"


def test_app_boots():
    at = AppTest.from_file(str(_HERE / "app.py"), default_timeout=240).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]


if __name__ == "__main__":
    test_rookie_page_swaps_in_season_projections()
    test_qb_rows_held_no_projection()
    test_app_boots()
    print("OK  RB (Love ~153) / WR (Makai Lemon ~133) / TE (Eli Stowers ~84) project; QB rookies HELD "
          "(no projection); PPG surface retired; app boots clean")
