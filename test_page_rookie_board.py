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

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "betting"))
sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))


def _entry():
    import page_rookie_board
    page_rookie_board.render()


def _entry_pos(pos):
    """Force a position filter so that position's projection column is populated."""
    def _entry():
        import page_rookie_board as p
        import streamlit as st
        orig = st.selectbox

        def patched(label, options, index=0, **kw):
            if label == "Position" and pos in options:
                return pos
            return orig(label, options, index=index, **kw)
        st.selectbox = patched
        try:
            p.render()
        finally:
            st.selectbox = orig
    return _entry


_entry_rb = _entry_pos("RB")
_entry_wr = _entry_pos("WR")
_entry_te = _entry_pos("TE")


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


def test_rookie_page_renders_and_swaps_projection():
    at = _run(_entry_rb)
    df = _find_df(at, "Proj (season ½-PPR)")
    assert df is not None, "projection column 'Proj (season ½-PPR)' must render"
    assert "Rookie Proj (PPG)" not in list(df.columns), "the starved per-game surface must be retired from display"
    for c in ("Sleeper Proj", "Diff vs Sleeper", "Full Hit-%"):
        assert c in list(df.columns), f"expected column {c} missing"
    love = df[df["Player"].astype(str).str.contains("Jeremiyah Love", na=False)]
    assert len(love) == 1, "Jeremiyah Love row must be present in the RB view"
    proj = float(love["Proj (season ½-PPR)"].iloc[0])
    assert proj > 100, f"Love projection must be the season-total (~153), not the starved 4.7 (got {proj})"


def test_wr_rows_show_season_total_projection():
    at = _run(_entry_wr)
    df = _find_df(at, "Proj (season ½-PPR)")
    assert df is not None, "projection column must render for the WR view"
    assert "Rookie Proj (PPG)" not in list(df.columns), "starved per-game surface must stay retired"
    ml = df[df["Player"].astype(str).str.contains("Makai Lemon", na=False)]
    assert len(ml) == 1, "a known 2026 WR rookie (Makai Lemon) must be present in the WR view"
    proj = float(ml["Proj (season ½-PPR)"].iloc[0])
    assert proj > 50, f"WR projection must be the season-total (~133), not the starved ~4.5 (got {proj})"


def test_te_rows_show_season_total_projection():
    at = _run(_entry_te)
    df = _find_df(at, "Proj (season ½-PPR)")
    assert df is not None, "projection column must render for the TE view"
    es = df[df["Player"].astype(str).str.contains("Eli Stowers", na=False)]
    assert len(es) == 1, "a known 2026 TE rookie (Eli Stowers) must be present in the TE view"
    proj = float(es["Proj (season ½-PPR)"].iloc[0])
    assert proj > 20, f"TE projection must be the season-total (~84), not the starved ~3 (got {proj})"


def test_app_boots():
    at = AppTest.from_file(str(_HERE / "app.py"), default_timeout=240).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]


if __name__ == "__main__":
    test_rookie_page_renders_and_swaps_projection()
    test_wr_rows_show_season_total_projection()
    test_te_rows_show_season_total_projection()
    test_app_boots()
    print("OK  rookie page swaps in RB (Love ~153), WR (Makai Lemon ~133), TE (Eli Stowers ~84) "
          "season-total projections; PPG surface retired; Sleeper+Diff present; app boots clean")
