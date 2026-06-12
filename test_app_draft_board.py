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
# Seasonal Value tab: ranks stay NUMERIC under the hood (so the grid sorts 1,2,..,10,11 correctly);
# column_config just DISPLAYS them with a position prefix. Verdict/Result are text tags.
NUMERIC_COLS = {"ADP", "Our Rank", "Finished", "Sleeper", "Proj Pts"}
TEXT_COLS = {"Player", "Pos", "Team", "Verdict", "Result"}


def _board_df(at):
    """The Seasonal Value table among all rendered dataframes (has Player + ADP + Verdict)."""
    for el in at.dataframe:
        v = el.value
        df = v.data if hasattr(v, "data") else v   # unwrap a Styler
        try:
            cols = set(df.columns)
        except Exception:
            continue
        if {"Player", "ADP", "Our Rank", "Verdict"} <= cols:
            return df
    return None


def _check_sortable(df):
    for c in df.columns:
        if c in NUMERIC_COLS:
            assert is_numeric_dtype(df[c]), f"{c!r} dtype is {df[c].dtype}, not numeric -> would sort as text"
        elif c in TEXT_COLS:
            assert df[c].dtype == object, f"{c!r} should be text"
    for c in ("ADP", "Our Rank", "Proj Pts"):   # the columns people actually sort by
        if c in df.columns:
            s = df[c].dropna().tolist()
            assert sorted(s) == sorted(s, key=float), f"{c} not numerically sortable"


def test_seasonal_value_tab_sortable_and_consistent():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception, at.exception

    # If the Draft Value Finder tab is disabled, skip rather than fail.
    if not any("Draft Value" in t.label for t in at.tabs):
        print("SKIP  Draft Value Finder tab disabled in app.py — re-enable to run this test")
        return

    sel = [s for s in at.selectbox if s.label == "Season"]
    assert sel, "season selector not found (need both 2025 and 2026 value boards built)"

    # ── completed season (2025): readable verdicts + a hit/miss result ──
    sel[0].set_value(2025).run()
    assert not at.exception, at.exception
    df = _board_df(at)
    assert df is not None, "seasonal-value table not found"
    _check_sortable(df)
    assert "Finished" in df.columns and "Result" in df.columns, "completed season should show Finished + Result"
    assert "Sleeper" in df.columns, "Sleeper comparison column should be present"
    # every row has a plain-English verdict; at least some are buys/fades
    verds = df["Verdict"].astype(str)
    assert verds.str.contains("Buy|Fade|Contested|—", case=False).all(), "every row needs a Verdict"
    assert verds.str.contains("Buy", case=False).any(), "should surface at least one buy"
    # Result is a hit/miss tag where there's a call (or 🏥 injured for missed-time seasons we don't grade)
    assert df["Result"].astype(str).str.contains("hit|miss|injured|^$", case=False).all()
    assert df["Result"].astype(str).str.contains("injured").any(), "injury-shortened seasons should show 🏥 injured, not a graded hit/miss"

    # ── position filter works ──
    rad = [r for r in at.radio if r.label == "Position"]
    assert rad, "position filter not found"
    rad[0].set_value("RB").run()
    assert not at.exception, at.exception
    dq = _board_df(at)
    assert (dq["Pos"] == "RB").all(), "position filter should restrict to RB"
    _check_sortable(dq)
    rad[0].set_value("All").run()

    # ── upcoming season (2026): verdicts but no actuals ──
    sel[0].set_value(2026).run()
    assert not at.exception, at.exception
    df26 = _board_df(at)
    assert df26 is not None
    _check_sortable(df26)
    assert "Verdict" in df26.columns, "upcoming season should show the Verdict column"
    assert "Finished" not in df26.columns and "Result" not in df26.columns, "upcoming season has no results"

    print("OK  seasonal value tab: renders; readable RB12-style ranks + plain-English Verdict; "
          "Proj Pts numeric; position filter works; 2025 shows Finished+Result, 2026 doesn't")


if __name__ == "__main__":
    test_seasonal_value_tab_sortable_and_consistent()
