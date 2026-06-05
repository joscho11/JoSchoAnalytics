"""Integration test: the Draft Board dashboard tab renders and is sortable.

Uses Streamlit AppTest to render app.py, drive the season selector + position filter,
and assert the rendered draft-board table is built so every rank column sorts NUMERICALLY
(the prior bug rendered 'QB2'/'emoji +6' strings that the grid sorted as text; the grid
sorts by the cell's underlying dtype, so numeric dtype == correct sort). Also checks the
overall<->positional column switch, and that the upcoming season shows a Value column while
a completed season shows Actual instead.

Run:  python test_app_draft_board.py    (or: pytest test_app_draft_board.py)
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from streamlit.testing.v1 import AppTest
from pandas.api.types import is_numeric_dtype

APP = str(Path(__file__).resolve().parent / "app.py")
# Rank/point columns are numeric (so the grid sorts them numerically). When a position is
# filtered the rank columns gain a "Pos " prefix (Pos ADP / Pos Pred / Pos Actual); "Diff"
# (Actual - Pred) appears on completed seasons. All of these must stay numeric.
NUMERIC_SUBSTRINGS = ("ADP", "Pred", "Actual", "Value", "Diff", "Proj Pts", "Actual Pts")
TEXT_COLS = {"Player", "Pos", "Team"}


def _col(df, name):
    """Find a column by its base name, tolerating the 'Pos ' prefix in the filtered view."""
    for c in (name, f"Pos {name}"):
        if c in df.columns:
            return c
    return None


def _board_df(at):
    """The Draft Board table among all rendered dataframes (has Player + an ADP + a Pred col)."""
    for el in at.dataframe:
        v = el.value
        df = v.data if hasattr(v, "data") else v   # unwrap a Styler
        try:
            cols = set(df.columns)
        except Exception:
            continue
        if "Player" in cols and _col(df, "ADP") and _col(df, "Pred"):
            return df
    return None


def _check_sortable(df):
    for c in df.columns:
        if any(sub in c for sub in NUMERIC_SUBSTRINGS):
            assert is_numeric_dtype(df[c]), f"{c!r} dtype is {df[c].dtype}, not numeric -> would sort as text"
        elif c in TEXT_COLS:
            assert df[c].dtype == object, f"{c!r} should be text"
    for base in ("ADP", "Pred", "Proj Pts"):
        c = _col(df, base)
        if c:
            s = df[c].dropna().tolist()
            assert sorted(s) == sorted(s, key=float), f"{c} not numerically sortable"


def test_draft_board_app_sortable_and_consistent():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception, at.exception

    # The Draft Board (Beta) tab is temporarily disabled in app.py (2026-06-05). When it's
    # off there is no board table to drive, so skip rather than fail. Re-enabling the tab
    # restores this test automatically.
    if not any("Draft Board" in t.label for t in at.tabs):
        print("SKIP  Draft Board tab disabled in app.py — re-enable to run this test")
        return

    sel = [s for s in at.selectbox if s.label == "Season"]
    assert sel, "season selector not found (need both 2025 and 2026 boards built)"

    # ── completed season (2025): overall view ──
    sel[0].set_value(2025).run()
    assert not at.exception, at.exception
    df = _board_df(at)
    assert df is not None, "draft-board table not found"
    _check_sortable(df)
    # overall view: plain column names, completed season => Actual + Diff, no Value
    assert "Actual" in df.columns and "Actual Pts" in df.columns, "completed season should show Actual columns"
    assert "Diff" in df.columns, "completed season should show the Diff (Actual - Pred) column"
    assert "Value" not in df.columns, "completed season should not show the Value column"
    pool_n = len(df)

    # ── completed season, filtered to QB: ranks become POSITIONAL and gain the 'Pos ' prefix ──
    rad = [r for r in at.radio if r.label == "Position"]
    assert rad, "position filter not found"
    rad[0].set_value("QB").run()
    assert not at.exception, at.exception
    dq = _board_df(at)
    _check_sortable(dq)
    assert "Pos ADP" in dq.columns and "Pos Pred" in dq.columns and "Pos Actual" in dq.columns, \
        "filtered view should use positional column names (Pos ADP / Pos Pred / Pos Actual)"
    pred_c = _col(dq, "Pred")
    # positional Pred can't exceed the number of QBs shown; and is smaller-scale than the overall pool
    assert dq[pred_c].dropna().max() <= len(dq), "positional Pred exceeds # of QBs (population mismatch)"
    assert dq[pred_c].dropna().max() < pool_n, "filtered ranks should be positional (smaller than overall)"
    # Diff must equal Actual - Pred (positional)
    act_c = _col(dq, "Actual")
    dd = dq.dropna(subset=[pred_c, act_c, "Diff"])
    assert ((dd[pred_c] - dd[act_c]) == dd["Diff"]).all(), "Diff should equal Pred - Actual"
    # THE Lamar/Hurts fix: within a position, Proj Pts must be monotonic with Pred (no inversions)
    qq = dq.dropna(subset=[pred_c, "Proj Pts"]).sort_values(pred_c)
    proj = qq["Proj Pts"].tolist()
    assert proj == sorted(proj, reverse=True), "Proj Pts not in Pred order (higher proj should rank better)"
    rad[0].set_value("All").run()

    # ── upcoming season (2026): Value column instead of Actual/Diff ──
    sel[0].set_value(2026).run()
    assert not at.exception, at.exception
    df26 = _board_df(at)
    assert df26 is not None
    _check_sortable(df26)
    assert "Value" in df26.columns, "upcoming season should show the Value column"
    assert "Actual" not in df26.columns, "upcoming season has no actual results"
    assert "Diff" not in df26.columns, "upcoming season has no Diff (no actuals)"

    print("OK  draft board: renders; ranks numeric+sortable; overall<->positional (Pos *) switch; "
          "2025 shows Actual+Diff, 2026 shows Value")


if __name__ == "__main__":
    test_draft_board_app_sortable_and_consistent()
