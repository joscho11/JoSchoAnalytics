from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import explore_wr_veteran_age as explore


def test_age_variants_are_bounded_and_only_drop_age_in_the_declared_arm():
    baseline = explore.VARIANTS["raw_age"]

    assert len(baseline) == 32
    assert len(explore.VARIANTS["cap_30"]) == len(baseline)
    assert len(explore.VARIANTS["cap_32"]) == len(baseline)
    assert len(explore.VARIANTS["drop_age"]) == len(baseline) - 1
    assert "age" not in explore.VARIANTS["cap_30"]
    assert "age" not in explore.VARIANTS["cap_32"]
    assert "age" not in explore.VARIANTS["drop_age"]
    assert explore.FIXED_LGBM == {"num_leaves": 31, "learning_rate": 0.06, "n_estimators": 400}
