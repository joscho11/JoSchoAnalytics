"""The PFF point-in-time join — red-before-green for the temporal leak found 2026-08-03.

THE DEFECT. `fantasy/rookie/harness/assemble_features.py::_load_pff` collapsed every PFF college row
with `groupby("norm_name")["season"].idxmax()` and merged on `norm_name` alone. The source season was
discarded BEFORE the join, so the latest college season carrying a name — often a different, later
player — was attached to every panel row with that name. Measured on the frozen 2014-2025 rookie
population: 963 receiving matches of which 20 drew from a season at or after the NFL rookie season,
and 308 RB rushing matches of which 8 did; 28 leaked (row, kind) pairs over 22 player-seasons.

Every test here reads FEATURES and identity only. No fantasy outcome is read, printed or compared.
The measured-example tests read the repo-owned frozen matrix, not the private PFF library, so they run
on a clean checkout with no network and no licensed data.
"""
import pathlib
import sys

import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
REPO = COACH.parent.parent.parent
HARNESS = REPO / "fantasy" / "rookie" / "harness"
sys.path.insert(0, str(COACH))
sys.path.insert(0, str(REPO / "fantasy" / "seasonal_projections"))

import assemble_real_panel_v39 as ARP                      # noqa: E402


def _production():
    """Import the REAL production feature builder. One shared implementation, not a copy."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("af_under_test", HARNESS / "assemble_features.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["af_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


AF = _production()


# =====================================================================================================
# The RETIRED rule, reproduced ONLY to prove the new one differs (red-before-green)
# =====================================================================================================
def retired_max_season_join(long, panel, kind, season_col):
    """The pre-2026-08-03 rule: max season per norm_name, season discarded, merge on name.

    Reproduced here verbatim in behaviour so the repair has a measured RED side. It is NEVER imported
    by production; `assemble_features.py` no longer contains it, and a test below asserts that.
    """
    idx = long.groupby("norm_name")["pff_season"].idxmax()
    fin = long.loc[idx].drop_duplicates("norm_name")
    out = panel[["norm_name", season_col]].merge(fin, on="norm_name", how="left")
    out.index = panel.index
    return out.rename(columns={"pff_season": f"pff_{kind}_source_season"})


def synth_long(rows, kind="receiving"):
    """rows = [(norm_name, pff_season, pff_player_id, pff_position, games, value)]"""
    df = pd.DataFrame(rows, columns=["norm_name", "pff_season", "pff_player_id", "pff_position",
                                     "pff_game_count", f"pff_{kind}_yprr"])
    return df


def synth_panel(rows):
    """rows = [(norm_name, season, position)]"""
    return pd.DataFrame(rows, columns=["norm_name", "season", "position"])


def pit(long, panel, kind="receiving"):
    sel = AF._pff_point_in_time(long, panel, kind, "season").set_index("_panel_ix")
    return sel.reindex(panel.index)


# =====================================================================================================
# RED — the retired rule leaks; GREEN — the shipped rule does not
# =====================================================================================================
LEAK_CASES = [
    # (label, panel rows, pff rows, old_selected_season, new_selected_season)
    ("mike evans 2014 -> 2021 receiving",
     [("mike evans", 2014, "WR")],
     [("mike evans", 2019, 1, "WR", 12, 2.1), ("mike evans", 2020, 1, "WR", 12, 2.2),
      ("mike evans", 2021, 1, "WR", 12, 2.3)],
     2021, None),
    ("michael thomas 2016 -> 2025 receiving",
     [("michael thomas", 2016, "WR")],
     [("michael thomas", 2014, 1, "WR", 12, 1.5), ("michael thomas", 2015, 1, "WR", 13, 2.7),
      ("michael thomas", 2025, 2, "WR", 11, 3.1)],
     2025, 2015),
    ("matt jones 2015 -> 2025 receiving",
     [("matt jones", 2015, "RB")],
     [("matt jones", 2014, 1, "HB", 11, 1.2), ("matt jones", 2023, 2, "HB", 4, 1.9),
      ("matt jones", 2024, 2, "HB", 7, 2.0), ("matt jones", 2025, 2, "HB", 13, 2.4)],
     2025, 2014),
]


@pytest.mark.parametrize("label,panel_rows,pff_rows,old_season,new_season", LEAK_CASES)
def test_RED_the_retired_rule_reproduces_each_measured_leak(label, panel_rows, pff_rows,
                                                            old_season, new_season):
    panel, long = synth_panel(panel_rows), synth_long(pff_rows)
    old = retired_max_season_join(long, panel, "receiving", "season")
    got = old["pff_receiving_source_season"].iloc[0]
    assert got == old_season, f"{label}: retired rule selected {got}, expected {old_season}"
    assert got >= panel["season"].iloc[0], f"{label}: this case must BE a leak to be a valid RED"


@pytest.mark.parametrize("label,panel_rows,pff_rows,old_season,new_season", LEAK_CASES)
def test_GREEN_the_shipped_rule_fixes_each_measured_leak(label, panel_rows, pff_rows,
                                                         old_season, new_season):
    panel, long = synth_panel(panel_rows), synth_long(pff_rows)
    got = pit(long, panel)["pff_receiving_source_season"].iloc[0]
    if new_season is None:
        assert pd.isna(got), f"{label}: expected NULL, got {got}"
    else:
        assert got == new_season, f"{label}: expected {new_season}, got {got}"
        assert got < panel["season"].iloc[0]


# =====================================================================================================
# The selection rule, clause by clause
# =====================================================================================================
def test_no_eligible_prior_season_yields_NULL():
    panel = synth_panel([("solo", 2016, "WR")])
    long = synth_long([("solo", 2016, 1, "WR", 12, 1.0), ("solo", 2017, 1, "WR", 12, 2.0)])
    assert pd.isna(pit(long, panel)["pff_receiving_source_season"].iloc[0])


def test_multiple_eligible_seasons_take_the_LATEST_prior():
    panel = synth_panel([("solo", 2019, "WR")])
    long = synth_long([("solo", 2016, 1, "WR", 12, 1.0), ("solo", 2017, 1, "WR", 12, 2.0),
                       ("solo", 2018, 1, "WR", 12, 3.0)])
    sel = pit(long, panel)
    assert sel["pff_receiving_source_season"].iloc[0] == 2018
    assert sel["pff_receiving_yprr"].iloc[0] == 3.0


@pytest.mark.parametrize("src,expected", [(2017, 2017), (2018, None), (2019, None)])
def test_the_season_boundary_is_STRICTLY_LESS_THAN(src, expected):
    """Exact boundary: a source season EQUAL to the rookie season is a leak, not an edge case."""
    panel = synth_panel([("solo", 2018, "WR")])
    long = synth_long([("solo", src, 1, "WR", 12, 5.0)])
    got = pit(long, panel)["pff_receiving_source_season"].iloc[0]
    assert (pd.isna(got) if expected is None else got == expected)


def test_a_LATER_same_name_player_can_never_match_an_earlier_rookie():
    """The core containment property, stated directly."""
    panel = synth_panel([("dup", 2016, "WR")])
    long = synth_long([("dup", 2020, 2, "WR", 12, 9.9), ("dup", 2021, 2, "WR", 12, 9.9)])
    assert pd.isna(pit(long, panel)["pff_receiving_source_season"].iloc[0])
    assert pd.isna(pit(long, panel)["pff_receiving_yprr"].iloc[0])


def test_a_same_name_collision_is_resolved_by_POSITION_when_that_is_decisive():
    """Two prior identities, one position-compatible: the compatible one wins.

    This is the real `jonathan williams` case — an RB whose name also belonged to a college WR. The
    retired rule attached the WR's later season to the RB.
    """
    panel = synth_panel([("jonathan williams", 2016, "RB")])
    long = synth_long([("jonathan williams", 2014, 10790, "HB", 13, 1.1),
                       ("jonathan williams", 2014, 21322, "WR", 6, 5.5),
                       ("jonathan williams", 2015, 21322, "WR", 3, 6.6)])
    sel = pit(long, panel)
    assert sel["pff_receiving_source_season"].iloc[0] == 2014
    assert sel["pff_receiving_yprr"].iloc[0] == 1.1, "the WR's row was attached to an RB"
    old = retired_max_season_join(long, panel, "receiving", "season")
    assert old["pff_receiving_source_season"].iloc[0] == 2015 and old["pff_receiving_yprr"].iloc[0] == 6.6


def test_a_same_name_collision_is_resolved_by_the_IMMEDIATELY_PRIOR_season():
    """Position does not separate them; exactly one identity played the season before entry."""
    panel = synth_panel([("dup", 2019, "RB")])
    long = synth_long([("dup", 2016, 1, "HB", 12, 1.0), ("dup", 2017, 1, "HB", 12, 2.0),
                       ("dup", 2018, 2, "HB", 12, 3.0)])
    sel = pit(long, panel)
    assert sel["pff_receiving_source_season"].iloc[0] == 2018
    assert sel["pff_receiving_yprr"].iloc[0] == 3.0


def test_an_UNRESOLVABLE_same_name_collision_yields_NULL_rather_than_a_guess():
    """Two identities, same position, both present in the season before entry -> NULL.

    This is the conservative branch and it has a measured cost: on the frozen population it nulls
    3 rushing blocks (matt jones 2015, tyree jackson 2021, zach evans 2023). Guessing between two
    same-name, same-position, same-season players is what produced the leak in the first place.
    """
    panel = synth_panel([("dup", 2016, "RB")])
    long = synth_long([("dup", 2015, 1, "HB", 11, 1.0), ("dup", 2015, 2, "HB", 1, 9.0)])
    sel = pit(long, panel)
    assert pd.isna(sel["pff_receiving_source_season"].iloc[0])
    assert pd.isna(sel["pff_receiving_yprr"].iloc[0])


def test_an_unambiguous_name_keeps_its_row_even_when_the_position_disagrees():
    """Position is a DISAMBIGUATOR, never a primary filter: a college WR who became an NFL RB keeps
    his row when no other identity claims the name."""
    panel = synth_panel([("solo", 2018, "RB")])
    long = synth_long([("solo", 2017, 1, "WR", 12, 4.4)])
    sel = pit(long, panel)
    assert sel["pff_receiving_source_season"].iloc[0] == 2017 and sel["pff_receiving_yprr"].iloc[0] == 4.4


def test_selection_is_deterministic_under_input_reordering():
    rows = [("dup", 2015, 1, "HB", 11, 1.0), ("dup", 2016, 1, "HB", 12, 2.0),
            ("dup", 2016, 1, "HB", 5, 3.0), ("dup", 2014, 1, "HB", 9, 4.0)]
    panel = synth_panel([("dup", 2018, "RB")])
    first = pit(synth_long(rows), panel).iloc[0].to_dict()
    for shuffled in ([rows[i] for i in (2, 0, 3, 1)], [rows[i] for i in (3, 2, 1, 0)]):
        again = pit(synth_long(shuffled), panel).iloc[0].to_dict()
        assert again == first, f"selection changed under input order: {again} != {first}"


# =====================================================================================================
# The production module itself
# =====================================================================================================
def test_the_retired_collapse_is_GONE_from_production():
    src = (HARNESS / "assemble_features.py").read_text(encoding="utf-8")
    needle = "groupby(" + '"norm_name"' + ")[" + '"season"' + "].idxmax()"
    assert needle not in src, "the retired non-temporal collapse is still in production"
    assert not hasattr(AF, "_load_pff"), "the retired _load_pff still exists"
    assert hasattr(AF, "_pff_long") and hasattr(AF, "_pff_point_in_time")


def test_build_features_REFUSES_a_panel_with_no_reference_season():
    """A join with no reference season cannot be point-in-time, so it must not run at all."""
    with pytest.raises(ValueError) as e:
        AF.build_features(pd.DataFrame({"gsis_id": ["x"], "position": ["WR"]}))
    assert "reference-season" in str(e.value)


def test_there_is_ONE_shared_production_join_not_a_generator_copy():
    """The matrix generator must CALL production, never reimplement the join."""
    gen = (REPO / "fantasy" / "seasonal_projections" / "build_rookie_arm0_features.py").read_text(
        encoding="utf-8")
    assert "build_features" in gen
    for banned in ("idxmax", "_pff_point_in_time", "groupby(\"norm_name\")", "PFF_RECV = ["):
        assert banned not in gen, f"the generator reimplements the PFF join ({banned})"


# =====================================================================================================
# The FROZEN ARTIFACT carries the guarantee — checkable with no private data
# =====================================================================================================
@pytest.fixture(scope="module")
def matrix():
    return pd.read_parquet(ARP.ROOKIE_MATRIX)


def test_the_artifact_carries_its_point_in_time_provenance(matrix):
    for c in ARP.ROOKIE_MATRIX_PROVENANCE:
        assert c in matrix.columns
    assert ARP.ROOKIE_MATRIX_PROVENANCE == ("pff_receiving_source_season", "pff_rushing_source_season")


@pytest.mark.parametrize("col", ARP.ROOKIE_MATRIX_PROVENANCE)
def test_NO_row_in_the_artifact_draws_from_its_own_season_or_later(matrix, col):
    nn = matrix[col].notna()
    assert int(nn.sum()) > 0, f"{col} is empty; the check would be vacuous"
    lag = matrix.loc[nn, "season"] - matrix.loc[nn, col]
    assert int(lag.min()) >= 1, f"{int((lag < 1).sum())} row(s) violate the point-in-time contract"


@pytest.mark.parametrize("kind,block", [("receiving", "pff_receiving_"), ("rushing", "pff_rushing_")])
def test_a_block_is_present_exactly_when_its_source_season_is(matrix, kind, block):
    """No orphan values: a PFF block without a recorded source season would be unverifiable."""
    cols = [c for c in matrix.columns if c.startswith(block) and not c.endswith("_source_season")]
    has_block = matrix[cols].notna().any(axis=1)
    has_src = matrix[f"pff_{kind}_source_season"].notna()
    assert int((has_block & ~has_src).sum()) == 0, "a PFF block has no recorded source season"


MEASURED_EXAMPLES = [
    # (norm_name, rookie season, block, retired source season, corrected source season)
    ("mike evans", 2014, "receiving", 2021, None),
    ("michael thomas", 2016, "receiving", 2025, 2015),
    ("matt jones", 2015, "receiving", 2025, 2014),
    ("matt jones", 2015, "rushing", 2025, None),
]


@pytest.mark.parametrize("name,season,kind,retired,corrected", MEASURED_EXAMPLES)
def test_each_measured_example_is_corrected_IN_THE_SHIPPED_ARTIFACT(matrix, name, season, kind,
                                                                    retired, corrected):
    row = matrix[(matrix["norm_name"] == name) & (matrix["season"] == season)]
    assert len(row) == 1, f"{name} {season} not uniquely in the frozen population"
    got = row[f"pff_{kind}_source_season"].iloc[0]
    assert retired >= season, "the retired value must be a leak for this to be a valid case"
    if corrected is None:
        assert pd.isna(got), f"{name} {season} {kind}: expected NULL, got {got}"
    else:
        assert got == corrected and got < season


def test_the_private_pff_inputs_are_fingerprinted_not_exposed():
    import json
    entry = json.loads(ARP.SNAPSHOT_MANIFEST.read_text(encoding="utf-8"))[
        ARP.ROOKIE_MATRIX_MANIFEST_KEY]
    pff = entry["pff_consumed"]
    assert pff["sha256"] == ARP.ROOKIE_MATRIX_PFF_SHA256 and len(pff["sha256"]) == 64
    assert pff["n_files"] == ARP.ROOKIE_MATRIX_PFF_FILES == 36
    assert sorted(pff["kinds"]) == ["passing", "receiving", "rushing"]
    assert pff["seasons"] == list(range(2014, 2026))
    # the manifest records a DIGEST and a file count, never a PFF value
    assert "player" not in json.dumps(pff).lower()


def test_the_superseded_leaked_artifact_is_recorded_as_INVALID():
    import json
    entry = json.loads(ARP.SNAPSHOT_MANIFEST.read_text(encoding="utf-8"))[
        ARP.ROOKIE_MATRIX_MANIFEST_KEY]
    sup = entry["supersedes"]
    assert sup["sha256"] == "4b4655abde1c63d6316db2277d2a5301360842c9cec94fea0c2c5d77f5252584"
    assert "INVALID" in sup["reason"] and sup["sha256"] != ARP.ROOKIE_MATRIX_SHA256


# =====================================================================================================
# ACTIVATION — the bundles were trained on the contaminated join, so readiness stays False
# =====================================================================================================
def test_the_rookie_features_are_now_COMPLETE_and_point_in_time():
    rows = {(r["position"], r["bucket"]): r for r in ARP.arm0_bucket_table()}
    for key in (("RB", "rookie"), ("WR", "rookie"), ("TE", "rookie")):
        assert rows[key]["features_available"] is True
        assert rows[key]["n_missing_from_declared_source"] == 0


def test_the_rookie_bundle_SPECS_are_complete_so_nothing_blocks_on_them():
    """WITHDRAWN BLOCKER. A v3.9o revision marked these buckets training-incompatible because the
    shipped estimators had been fit on the leaked join. `fit_predict` builds a fresh estimator every
    fold and never touches the serialized object, so that blocker was false; see
    `test_arm0_refits_from_scratch_v39.py`. What is checked instead is the bundle SPECIFICATION.
    """
    rows = {(r["position"], r["bucket"]): r for r in ARP.arm0_bucket_table()}
    for key in rows:
        assert rows[key]["spec_contract_ok"] is True and rows[key]["spec_problems"] == []
        assert rows[key]["complete"] is True
    assert not hasattr(ARP, "CONTAMINATED_TRAINED_BUCKETS")
    assert not hasattr(ARP, "ROOKIE_BUNDLE_TRAINING_BLOCKER")


def test_activation_readiness_is_TRUE_now_that_the_features_are_point_in_time():
    ok, detail = ARP.activation_readiness()
    assert ok is True, detail
    assert "all 7 shipped Arm 0 buckets" in detail
    assert "NOT AUTHORIZED" in detail


def test_the_frozen_hyperparameter_limitation_is_disclosed_but_does_not_gate():
    """The one real residue of the leak for Arm 0: the fixed hyperparameters were tuned under the old
    pipeline. Common to every arm, so it cannot differentially favour one — disclosed, not gated."""
    d = ARP.FROZEN_HYPERPARAMETER_DISCLOSURE
    assert "frozen pre-experiment" in d and "does not retune" in d and "NOT gated" in d
    assert ARP.activation_readiness()[0] is True


def test_the_bundles_themselves_were_not_touched():
    """No retraining happened in this pass: the pinned pool hashes are unchanged."""
    import arm0_bundle_pins as PINS
    import hashlib
    import pickle
    for (pos, bucket), pin in PINS.BUNDLE_FEATURE_PINS.items():
        fname = ARP.SHIPPED_ARM0_BUCKETS[(pos, bucket)][0]
        fc = tuple(pickle.loads((ARP.MODELS_DIR / fname).read_bytes())["feature_cols"])
        assert fc == tuple(pin["feature_cols"])
        assert hashlib.sha256("\n".join(fc).encode("utf-8")).hexdigest() == pin["sha256"]


def test_the_gate_still_refuses_and_the_locks_are_still_shut():
    import run_coach_projection_experiment_v39 as EX
    pf = EX.preflight(pipeline_assertions={k: 3 for k in EX._PIPELINE_ASSERTIONS})
    assert pf["all_ok"] is True and pf["n_checks"] == 21 and pf["n_failed"] == 0
    assert ARP.authorized_real_gate(pf)[0] is False
    assert EX.REAL_FIT_AUTHORIZED is False
    assert EX.real_fit_lock_state() == (False, False)
