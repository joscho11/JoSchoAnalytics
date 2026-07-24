"""Talent columns + compliance guard for the rebuilt Draft Board tab (2026-07-22).

The licensed Phase-4 band and its H7 layout-adjacency fence were retired with Joseph's
decision to make the tab a season-projection comparison table (the Model Gap deliberately
combines the model projection with the draft market). What remains enforced here:
  • the two talent columns are present and DISJOINT (a row never carries both an NFL and a
    College talent score — they are different scales);
  • no derived column NAME fuses a talent score with a gap column;
  • the daily ADP refresh never touches the talent artifacts;
  • the whole app still renders.
The board copy's forbidden-language scan lives in test_board_page.py (rendered-text scan).
"""
import os
import re
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


def _board_df():
    import draft_board_2026 as db
    db._load_board_2026.clear()
    return db._load_board_2026()


def test_talent_columns_present_and_disjoint():
    df = _board_df()
    for c in ("nfl_talent", "college_talent"):
        assert c in df.columns, c
    import pandas as pd
    both = df[df.nfl_talent.notna() & df.college_talent.notna()]
    assert both.empty, f"rows with BOTH talent scores populated: {both.player.tolist()}"


def test_no_derived_column_fuses_talent_with_gap():
    import draft_board_2026 as db
    df = _board_df()
    talent = re.compile(r"talent", re.I)
    gap = re.compile(r"gap", re.I)
    for c in df.columns:
        assert not (talent.search(c) and gap.search(c)), \
            f"derived column fuses a talent score with a gap: {c}"
    for label, key in db.SORT_KEYS.items():
        assert not (talent.search(key) and gap.search(key)), (label, key)


def test_refresh_excludes_talent_artifacts():
    src = (_HERE / "fantasy" / "seasonal_projections" / "refresh_board_adp.py") \
        .read_text(encoding="utf-8", errors="ignore")
    assert "talent_score_2026" not in src and "rookie_score_2026" not in src
    wf = _HERE / ".github" / "workflows" / "board_refresh.yml"
    if wf.exists():
        y = wf.read_text(encoding="utf-8", errors="ignore")
        assert "talent_score_2026" not in y and "rookie_score_2026" not in y


def test_app_renders_all_tabs():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(_HERE / "app.py"), default_timeout=180).run()
    assert len(at.exception) == 0, [str(e) for e in at.exception]
    assert len(at.error) == 0, [str(e) for e in at.error]
