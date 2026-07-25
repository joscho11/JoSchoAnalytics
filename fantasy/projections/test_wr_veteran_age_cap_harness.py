from pathlib import Path
import sys

import pandas as pd


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wr_veteran_age_cap_harness as harness


def test_challenger_replaces_only_age_at_the_pinned_position():
    challenger = harness.challenger_features()

    assert len(challenger) == 32
    assert challenger.index(harness.CHALLENGER_AGE_COL) == harness.FROZEN_BASELINE_FEATURES.index("age")
    assert "age" not in challenger
    assert all(
        base == candidate or (base == "age" and candidate == harness.CHALLENGER_AGE_COL)
        for base, candidate in zip(harness.FROZEN_BASELINE_FEATURES, challenger)
    )
    assert harness.current_veteran_features() == harness.FROZEN_BASELINE_FEATURES


def test_structural_panel_caps_age_without_target_or_market_columns(tmp_path):
    path = tmp_path / "season_dataset.csv"
    rows = []
    for season in harness.TEST_SEASONS:
        for idx, age in enumerate((29.0, 30.0, 34.0)):
            row = {"player_id": f"p{season}_{idx}", "position": "WR", "is_rookie": 0,
                   "season": season, "age": age}
            for feature in harness.FROZEN_BASELINE_FEATURES:
                row.setdefault(feature, 1.0)
            row["sleeper_pts_half_ppr"] = 999.0
            row["adp_pos_rank"] = 1.0
            rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)

    panel = harness.load_structural_panel(path)

    assert "sleeper_pts_half_ppr" not in panel.columns
    assert "adp_pos_rank" not in panel.columns
    assert panel[harness.CHALLENGER_AGE_COL].tolist()[:3] == [29.0, 30.0, 30.0]
