"""One flagged set: fantasy default ranking, DFS pool, and the producer mask agree."""
import importlib.util
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_ROOT = _HERE.parent
sys.path[:0] = [str(_HERE), str(_HERE / "site_pages")]

import dfs_runtime  # noqa: E402
import page_weekly_fantasy as weekly  # noqa: E402

WEEKLY_SRC = _ROOT / "nfl_fantasy_weekly_projections_v2_prod" / "independent_model" / "src" / "review_gate.py"
DFS_TESTS = _ROOT / "dfs_optimizer_v1_prod" / "tests"
STATUSES = ["clear", "flagged", "needs_review", "include", "exclude"]


def _producer_mask(frame):
    if not WEEKLY_SRC.is_file():
        pytest.skip("weekly producer checkout absent")
    spec = importlib.util.spec_from_file_location("review_gate_producer", WEEKLY_SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.default_excluded_mask(frame)


def _frame():
    return pd.DataFrame({
        "player_id": [f"p{i}" for i in range(5)],
        "player_display_name": [f"Player {i}" for i in range(5)],
        "position": "RB", "team": "SEA", "opponent_team": "CHI", "projected_pts": 8.0,
        "review_status": STATUSES,
        "review_reason": ["", "role_collapse_zero_use_active_last_game", "availability_evidence_missing",
                          "role_collapse_zero_use_active_last_game", "role_collapse_zero_use_active_last_game"],
        "review_original_projected_pts": [None, 8.0, 8.0, 8.0, 8.0],
    })


def test_all_three_masks_flag_the_same_players():
    frame = _frame()
    pipeline = dfs_runtime.load_pipeline()
    expected = [False, True, True, False, True]
    assert weekly._review_hidden(frame).tolist() == expected
    assert pipeline.review_excluded_mask(frame).tolist() == expected
    assert _producer_mask(frame).tolist() == expected
    kept = weekly.eligible_board_rows(frame, 2026, 9)
    assert kept.player_id.tolist() == ["p0", "p3"]
    shown = weekly.eligible_board_rows(frame, 2026, 9, include_review_hidden=True)
    assert len(shown) == 5


def test_same_flagged_set_leaves_fantasy_ranking_and_dfs_pool():
    if not (DFS_TESTS / "test_pipeline.py").is_file():
        pytest.skip("dfs producer checkout absent")
    sys.path.insert(0, str(DFS_TESTS))
    from test_pipeline import _frames

    pipeline = dfs_runtime.load_pipeline()
    dk, proj = _frames()
    proj = proj.copy()
    proj["team"] = proj["team"]
    flagged = {"Demo RB 1": "flagged", "Demo WR 2": "needs_review", "Demo TE 1": "exclude", "Demo WR 4": "include"}
    proj["review_status"] = proj.player_display_name.map(flagged).fillna("clear")
    proj["review_reason"] = proj.review_status.map(lambda s: "" if s == "clear" else "availability_evidence_missing")
    pool = pipeline.build_pool_frames(dk, proj)
    dfs_excluded = set(pool.loc[pool.exclusion_reason.str.startswith("review:"), "name"])
    fantasy_hidden = set(proj.loc[weekly._review_hidden(proj), "player_display_name"])
    assert dfs_excluded == fantasy_hidden == {"Demo RB 1", "Demo WR 2", "Demo TE 1"}
    ranking = weekly.eligible_board_rows(proj.assign(position=proj.position.where(proj.position != "DST", "QB")), 2026, 1)
    assert not set(ranking.player_display_name) & dfs_excluded


def _render_with_review(tmp_path):
    src_path = weekly.available_projection_files()[max(k for k in weekly.available_projection_files() if k[0] == 2026)]
    season, week = max(k for k in weekly.available_projection_files() if k[0] == 2026)
    frame = pd.read_csv(src_path)
    frame["review_status"] = "clear"
    frame["review_reason"] = ""
    frame["review_original_projected_pts"] = float("nan")
    held = frame.sort_values("projected_pts", ascending=False).index[[3, 9]]
    frame.loc[held, "review_status"] = ["flagged", "needs_review"]
    frame.loc[held, "review_reason"] = ["role_collapse_zero_use_active_last_game", "availability_evidence_missing"]
    frame.loc[held, "review_original_projected_pts"] = frame.loc[held, "projected_pts"]
    path = tmp_path / f"projections_{season}_week{week:02d}.csv"
    frame.to_csv(path, index=False)
    h = tmp_path / "h.py"
    h.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_HERE / 'site_pages'}']\n"
        "from pathlib import Path\nimport page_weekly_fantasy as p\n"
        f"p.available_projection_files = lambda: {{({season}, {week}): Path(r'{path}')}}\n"
        f"p.page_common.release_default_selection = lambda *a, **k: ({season}, {week})\n"
        "p.page_common.render_release_status = lambda *a, **k: None\n"
        "p.render()\n", encoding="utf-8")
    original = weekly.available_projection_files
    common = weekly.page_common
    saved = (common.release_default_selection, common.render_release_status)
    try:
        at = AppTest.from_file(str(h), default_timeout=180).run()
    finally:
        weekly.available_projection_files = original
        common.release_default_selection, common.render_release_status = saved
    return at, frame.loc[held, "player_display_name"].tolist()


def test_weekly_page_hides_flagged_by_default_with_expander(tmp_path):
    at, names = _render_with_review(tmp_path)
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    held_frame = next(df.value for df in at.dataframe if "Reason" in df.value.columns)
    assert set(held_frame["Player"]) == set(names)
    assert {"Status", "Original proj"} <= set(held_frame.columns)
    assert not held_frame["Reason"].str.contains("injur", case=False).any()
    ranked = pd.concat([df.value for df in at.dataframe if "Reason" not in df.value.columns])
    assert not set(ranked["Player"]) & set(names)
