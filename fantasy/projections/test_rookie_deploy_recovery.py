from pathlib import Path
import sys

import pandas as pd
import pytest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "seasonal_projections"))

import rookie_deploy_recovery as recovery


def _sources(tmp_path):
    seas = tmp_path / "seasonal_projections"
    pff = seas / "pff" / "college_2025"
    pff.mkdir(parents=True)
    pd.DataFrame({"norm_name": ["test prospect"], "cfb_final_dom": [0.22]}).to_csv(
        seas / "college_features.csv", index=False
    )
    pd.DataFrame({"player": ["Test Prospect"], "yards": [811.0]}).to_csv(
        pff / "college_receiving_summary_2025.csv", index=False
    )
    return seas


def test_recovers_all_empty_deploy_profile_from_existing_sources(tmp_path, monkeypatch):
    seas = _sources(tmp_path)
    monkeypatch.setattr(recovery, "SEAS", seas)
    monkeypatch.setattr(recovery, "PFF", seas / "pff")
    monkeypatch.setattr(recovery, "PFF_SEASONS", [2025])
    rook = pd.DataFrame({
        "season": [2026, 2025], "norm_name": ["test prospect", "test prospect"],
        "player": ["Test Prospect", "Historical Prospect"], "draft_pick": [33.0, 40.0],
        "cfb_final_dom": [pd.NA, pd.NA], "pff_receiving_yards": [pd.NA, pd.NA],
    })

    out = recovery.recover_missing_deploy_profiles(
        rook, ["cfb_final_dom", "pff_receiving_yards"], "receiving"
    )

    assert out.loc[0, "cfb_final_dom"] == pytest.approx(0.22)
    assert out.loc[0, "pff_receiving_yards"] == pytest.approx(811.0)
    assert pd.isna(out.loc[1, "cfb_final_dom"])
    recovery.assert_drafted_deploy_profiles(
        out, ["cfb_final_dom", "pff_receiving_yards"], drafted_names={"test prospect"}
    )


def test_guard_rejects_drafted_deploy_rookie_without_any_profile():
    rook = pd.DataFrame({
        "season": [2026], "norm_name": ["unmatched"], "player": ["Unmatched Rookie"],
        "draft_pick": [200.0], "cfb_final_dom": [pd.NA], "pff_receiving_yards": [pd.NA],
    })

    with pytest.raises(AssertionError, match="Unmatched Rookie"):
        recovery.assert_drafted_deploy_profiles(
            rook, ["cfb_final_dom", "pff_receiving_yards"], drafted_names={"unmatched"}
        )
