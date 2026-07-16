"""Talent/Rookie two-cell board columns — layout fence + render test (Phase 3).

H7 fence: the Talent/Rookie columns are context-only and must never combine with
the disagreement/gap column, bands, P(top-N), or bust probability — in code,
derived columns, or layout adjacency.
"""
import os
import re
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

HERE = Path(__file__).resolve().parent


def _board_df():
    import draft_board_2026 as db
    db._load_board_2026.clear()
    return db._load_board_2026()


def test_two_cell_columns_present_and_disjoint():
    df = _board_df()
    for c in ["talent_disp", "rookie_disp", "talent_score_num", "rookie_score_num",
              "cell_note", "talent_w", "college_share"]:
        assert c in df.columns, c
    both = df[(df.talent_disp != "–") & (df.rookie_disp != "–")]
    assert both.empty, f"rows with BOTH cells populated: {both.player.tolist()}"
    hunter = df[df.player_id == "00-0040718"]
    assert not hunter.empty and (hunter.iloc[0].talent_disp != "–"), \
        "R22: Travis Hunter must carry a Talent Score cell"


def test_h7_layout_fence_no_derived_mixing():
    import draft_board_2026 as db
    df = _board_df()
    fence = re.compile(r"(talent|rookie)", re.I)
    signal = re.compile(r"(gap|top12|top24|bust|p_top|value)", re.I)
    for c in df.columns:
        assert not (fence.search(c) and signal.search(c)), \
            f"derived column mixes talent/rookie with the value signal: {c}"
    # no sort key joins them; no combined key exists
    for label, key in db.SORT_KEYS.items():
        assert not (fence.search(key) and signal.search(key)), (label, key)
    # adjacency: the two new columns sit at the END of COLUMN_META, not beside Gap
    keys = [m[0] for m in db.COLUMN_META]
    gap_i = keys.index("gap_disp")
    for c in ("talent_disp", "rookie_disp"):
        assert keys.index(c) - gap_i >= 3, f"{c} placed too near the Gap column"


def test_refresh_and_workflow_exclusion():
    src = (HERE / "fantasy" / "seasonal_projections" / "refresh_board_adp.py"
           ).read_text(encoding="utf-8", errors="ignore")
    assert "talent_score_2026" not in src and "rookie_score_2026" not in src
    wf = HERE / ".github" / "workflows" / "board_refresh.yml"
    if wf.exists():
        y = wf.read_text(encoding="utf-8", errors="ignore")
        assert "talent_score_2026" not in y and "rookie_score_2026" not in y


def test_app_renders_all_tabs():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(HERE / "app.py"), default_timeout=180).run()
    assert len(at.exception) == 0, [str(e) for e in at.exception]
    assert len(at.error) == 0, [str(e) for e in at.error]
