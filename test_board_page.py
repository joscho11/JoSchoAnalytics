"""Proof for the Draft Board page after the st.dataframe revert (the st.table
experiment was rejected). Drives the pre-season entrypoint so the board is the default
page. Hermetic (APP_OFFLINE=1).

Asserts: the board renders via st.dataframe (NOT st.table); the "What each column means"
guide lives INSIDE the How-to-read expander which is collapsed on load; all 180 rows
render in the scroll box (no Top-40 cap); sentinels (Gainwell blank Gap) sink to the
bottom via the default Gap-desc Sort-by path; display strings are intact; and the CSV
download (full board, on-screen headers) is present. The numeric-sort guarantee itself is
covered by test_app_draft_board.py::test_board_sort_is_numeric_and_sentinels_sink.
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"
os.environ["BOARD_REFRESH_SEASON_START"] = "2099-01-01"   # force pre-season -> board default

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
ENTRY = str(_HERE / "app.py")   # the multipage entrypoint (post-3e swap)


def _run():
    at = AppTest.from_file(ENTRY, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _board_df(at):
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            if "player_disp" in list(d.columns):
                return d
        except Exception:
            pass
    return None


def test_board_uses_dataframe_not_table():
    at = _run()
    assert len(list(at.table)) == 0, "board reverted to st.dataframe — no st.table"
    assert _board_df(at) is not None, "board must render via st.dataframe"


def test_column_guide_inside_collapsed_expander():
    at = _run()
    exps = [e for e in at.expander if "How to read" in str(getattr(e, "label", ""))]
    assert exps, "How-to-read expander missing"
    assert exps[0].proto.expanded is False, "How-to-read expander must be collapsed on load"
    md = " ".join(str(m.value) for m in at.markdown)
    assert "What each column means" in md, "column guide missing"
    # a COLUMN_META tooltip string appears in the guide (relocated byte-identical)
    assert "no gap available for this row" in md, "a COLUMN_META tooltip must appear in the guide"


def test_full_board_no_cap_sentinels_sink_strings_intact():
    at = _run()
    # no Top-40 cap / Show-all toggle anymore
    assert not any(getattr(c, "key", None) == "db26_showall" for c in at.checkbox), \
        "the Show-all toggle must be gone (scroll box replaces the row cap)"
    t = _board_df(at)
    assert t.shape[0] == 180, "all 180 rows render inside the scroll box"
    # default Gap-desc -> Gainwell (blank gap '–') sits last
    assert t["gap_disp"].iloc[-1] == "–", "blank-gap sentinel must be last on default Gap-desc"
    assert int((t["gap_disp"] == "–").sum()) == 1
    assert int((t["eff_disp"] == "Rookie").sum()) == 14
    # Expected cell drops the redundant "%ile" (now stated in the header
    # "Expected (Percentile)") but keeps the parenthesized ordinal, e.g. "112 (39th)".
    assert not t["p50_disp"].str.contains("%ile").any(), \
        "Expected cell must drop the %ile suffix (moved to the header)"
    assert t["p50_disp"].str.contains(r"\(\d+(?:st|nd|rd|th)\)").any(), \
        "Expected cell keeps the parenthesized percentile ordinal, e.g. '(39th)'"


def test_csv_download_present():
    at = _run()
    dl = at.get("download_button")
    assert any("Download board (CSV)" in b.label for b in dl), "full-board CSV download missing"


if __name__ == "__main__":
    test_board_uses_dataframe_not_table()
    test_column_guide_inside_collapsed_expander()
    test_full_board_no_cap_sentinels_sink_strings_intact()
    test_csv_download_present()
    print("OK  board reverted to st.dataframe; guide collapsed; 180 rows; sentinels sink; CSV present")
