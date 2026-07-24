"""Proof for the rebuilt Draft Board tab (2026-07-22): the licensed Phase-4 band was
retired and the tab is now a 245-row season-projection comparison table (Sleeper ADP +
Position Rank + two independent projections with their positional-rank gaps + descriptive
talent scores). Renders the board page function directly via AppTest.from_function
(nav-independent). Hermetic (APP_OFFLINE=1).

Asserts: renders via st.dataframe (not st.table); the "What each column means" guide lives
INSIDE the collapsed How-to-read expander; all 245 rows render; the default sort is Sleeper
ADP ascending; the two un-projected rookie QBs are KEPT with a blank Model Proj; the exact
on-screen column labels are present; the CSV download exists; and the rendered copy carries no
forbidden buy/sell/value language.
"""
import os
import re
import sys
from pathlib import Path

import pandas as pd

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "betting"))
sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))

_FORBIDDEN = re.compile(
    r"\b(buy|sell|fade|steal|reach|target|tier|must[- ]?draft|overvalued|undervalued|"
    r"hit[- ]?rate|accuracy)\b", re.I)


def _entry():
    """Board page as a standalone AppTest script (nav-independent)."""
    import page_draft_board
    page_draft_board.render()


def _run():
    at = AppTest.from_function(_entry, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _board_df(at):
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            if {"adp_half_ppr", "model_gap"} <= set(d.columns):
                return d
        except Exception:
            pass
    return None


def test_board_uses_dataframe_not_table():
    at = _run()
    assert len(list(at.table)) == 0, "board must render via st.dataframe, not st.table"
    assert _board_df(at) is not None, "board dataframe not found"


def test_column_guide_inside_collapsed_expander():
    at = _run()
    exps = [e for e in at.expander if "How to read" in str(getattr(e, "label", ""))]
    assert exps, "How-to-read expander missing"
    assert exps[0].proto.expanded is False, "How-to-read expander must be collapsed on load"
    md = " ".join(str(m.value) for m in at.markdown)
    assert "What each column means" in md, "column guide missing"
    # a COLUMN_META tooltip string appears in the guide (relocated byte-identical)
    assert "descriptive difference, not advice" in md, \
        "a COLUMN_META tooltip must appear in the guide"


def test_full_board_245_default_adp_ascending_rookie_qbs_kept():
    at = _run()
    t = _board_df(at)
    assert t.shape[0] == 245, f"expected 245 rows in the scroll box, got {t.shape[0]}"
    adp = t["adp_half_ppr"].to_numpy()
    assert (adp[:-1] <= adp[1:]).all(), "default sort must be Sleeper ADP ascending"
    # the two un-projected rookie QBs are KEPT (not dropped), blank in Model Proj
    n_blank_model = int(pd.isna(t["model_proj"]).sum())
    assert n_blank_model == 2, f"expected exactly 2 blank Model Proj rows, got {n_blank_model}"
    # Sleeper Proj is blank for the same two (their only non-blank cells are ADP-derived)
    assert int(pd.isna(t["sleeper_proj"]).sum()) == 2


def test_exact_column_labels_present():
    import draft_board_2026 as board
    labels = [m[2] for m in board.COLUMN_META]
    for want in ("Sleeper ADP", "Position Rank", "Sleeper Proj Position Rank", "Sleeper Gap",
                 "Model Proj Position Rank", "Model Gap", "Sleeper Proj", "Model Proj",
                 "NFL Talent Score", "College Talent Score"):
        assert want in labels, f"missing exact column label: {want!r}"


def test_semantic_gap_colors_and_active_sort_tint():
    """The rebuilt table keeps the established Weekly Fantasy visual language.

    Gap direction is semantic (negative red, positive green); ranks use the same
    red-to-green ramp; the server-authoritative Sort by control marks its active
    column independently with a soft green surface tint.
    """
    import draft_board_2026 as board

    df = board._load_board_2026()
    view = board._sort_board(df, "Model Gap", ascending=False)
    styler = view[board._DISPLAY_COLS].style.apply(
        board._style_board(view, df, "model_gap"), axis=None)
    ctx = styler._compute().ctx

    model_gap_col = view[board._DISPLAY_COLS].columns.get_loc("model_gap")
    sleeper_gap_col = view[board._DISPLAY_COLS].columns.get_loc("sleeper_gap")
    model_proj_col = view[board._DISPLAY_COLS].columns.get_loc("model_proj")

    active_style = dict(ctx[(0, model_gap_col)])
    assert active_style["background-color"] == "#16281f"
    assert active_style["font-weight"] == "700"
    assert active_style["font-size"] == "15px"

    # Find a non-null negative model gap and a non-null positive Sleeper gap to
    # prove the two independently-computed disagreement columns keep direction.
    neg_i = next(i for i, v in enumerate(view["model_gap"]) if v < 0)
    pos_i = next(i for i, v in enumerate(view["sleeper_gap"]) if v > 0)
    def _rgb(value):
        return tuple(int(x) for x in value.removeprefix("rgb(").removesuffix(")").split(","))

    neg_rgb = _rgb(dict(ctx[(neg_i, model_gap_col)])["color"])
    pos_rgb = _rgb(dict(ctx[(pos_i, sleeper_gap_col)])["color"])
    assert neg_rgb[0] > neg_rgb[1], "negative gaps must lean red"
    assert pos_rgb[1] > pos_rgb[0], "positive gaps must lean green"
    assert (pos_i, model_proj_col) not in ctx or "color" not in dict(ctx[(pos_i, model_proj_col)])


def test_no_forbidden_language_in_rendered_copy():
    at = _run()
    text = " ".join(str(m.value) for m in at.markdown)
    hits = _FORBIDDEN.findall(text)
    assert not hits, f"forbidden language in rendered board copy: {hits}"


def test_csv_download_present():
    at = _run()
    dl = at.get("download_button")
    assert any("Download board (CSV)" in b.label for b in dl), "full-board CSV download missing"


if __name__ == "__main__":
    test_board_uses_dataframe_not_table()
    test_column_guide_inside_collapsed_expander()
    test_full_board_245_default_adp_ascending_rookie_qbs_kept()
    test_exact_column_labels_present()
    test_semantic_gap_colors_and_active_sort_tint()
    test_no_forbidden_language_in_rendered_copy()
    test_csv_download_present()
    print("OK  rebuilt board: st.dataframe; guide collapsed; 245 rows; ADP-asc default; "
          "2 rookie QBs kept blank; exact labels; no forbidden language; CSV present")
