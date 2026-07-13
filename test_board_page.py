"""Batch-2 proof for the new Draft Board page (st.table view via page_draft_board /
draft_board_2026.render(use_table=True)). Drives the pre-season entrypoint so the board
is the default page. Hermetic (APP_OFFLINE=1).

Asserts: the default board renders via st.table (no st.dataframe); Top-40 default with a
working "Show all" expand to 180; sentinels (Gainwell blank Gap) sink to the bottom
against the st.table render; display strings survive byte-identical (Gap '–', Rookie,
the Expected '%ile' suffix). The numeric-sort guarantee itself is covered unchanged by
test_app_draft_board.py::test_board_sort_is_numeric_and_sentinels_sink.
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"
os.environ["BOARD_REFRESH_SEASON_START"] = "2099-01-01"   # force pre-season -> board default

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
ENTRY = str(_HERE / "app_multipage.py")


def _run():
    at = AppTest.from_file(ENTRY, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _table(at):
    for el in at.table:
        v = el.value
        return v.data if hasattr(v, "data") else v
    return None


def _show_all(at):
    cb = [c for c in at.checkbox if c.key == "db26_showall"]
    assert cb, "Show-all toggle missing"
    return cb[0].set_value(True).run()


def test_board_uses_static_table_not_dataframe():
    at = _run()
    assert len(list(at.table)) >= 1, "board default view must render via st.table"
    assert len(list(at.dataframe)) == 0, "default board view must not use st.dataframe"


def test_top40_default_and_show_all_180():
    at = _run()
    t = _table(at)
    assert t is not None and t.shape[0] == 40, \
        f"Top-40 default expected; got {None if t is None else t.shape}"
    at = _show_all(at)
    assert _table(at).shape[0] == 180, "Show-all should render all 180 rows"


def test_sentinels_sink_and_strings_intact_in_table():
    at = _show_all(_run())
    t = _table(at)
    # default sort is Gap-descending; the blank-gap sentinel (Gainwell) sits last
    assert t["Gap"].iloc[-1] == "–", \
        f"blank-gap sentinel must be last on the st.table; got {t['Gap'].iloc[-1]!r}"
    # display strings byte-identical through the Styler
    assert int((t["Gap"] == "–").sum()) == 1
    assert int((t["NFL Efficiency %ile (pos)"] == "Rookie").sum()) == 14
    assert int((t["NFL Efficiency %ile (pos)"] == "–").sum()) == 18
    assert t["Expected"].str.contains("%ile").any(), "Expected must keep the %ile suffix"


if __name__ == "__main__":
    test_board_uses_static_table_not_dataframe()
    test_top40_default_and_show_all_180()
    test_sentinels_sink_and_strings_intact_in_table()
    print("OK  board page: st.table, Top-40 default + Show-all, sentinels sink, strings intact")
