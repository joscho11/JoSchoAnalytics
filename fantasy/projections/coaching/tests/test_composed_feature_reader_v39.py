"""THE COMPOSED FEATURE READER — the frozen SHIPPED_ARM0_BUCKETS routing, implemented.

`SHIPPED_ARM0_BUCKETS` already assigns the four VETERAN buckets to the veteran snapshot and the
RB/WR/TE ROOKIE buckets to the rookie matrix. This is that contract, not a new design choice.

The veteran snapshot is the population and routing SPINE. The rookie matrix supplies the RB/WR/TE
rookie-bucket rows, whose key set must equal the spine's `is_rookie == 1` RB/WR/TE rows EXACTLY.
QB/rookie is absent from the mapping (the arm was HELD) and keeps veteran-source values.

NINE columns live in both sources. Ownership is explicit and per row: a rookie row takes the ROOKIE
value for every one of them, INCLUDING a NULL — nothing is coalesced.

No fantasy outcome is read anywhere here. Both sources are feature-only by construction.
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COACH))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import arm0_bundle_pins as PINS                            # noqa: E402
import assemble_real_panel_v39 as ARP                      # noqa: E402
import run_coach_projection_experiment_v39 as EX           # noqa: E402
import write_v39_results as WR                             # noqa: E402

KEYS = list(ARP.PANEL_KEYS)
EXPECTED_ROOKIE_ROWS = 1263
EXPECTED_SPINE_ROWS = 7350
EXPECTED_QB_ROOKIE_ROWS = 117
EXPECTED_BUCKET_ROWS = {("QB", "veteran"): 885, ("RB", "veteran"): 1496, ("WR", "veteran"): 2266,
                        ("TE", "veteran"): 1323, ("RB", "rookie"): 387, ("WR", "rookie"): 584,
                        ("TE", "rookie"): 292}


@pytest.fixture(scope="module")
def spine():
    return pd.read_parquet(ARP.VETERAN_SNAPSHOT, columns=list(ARP.VETERAN_FEATURE_COLUMNS))


@pytest.fixture(scope="module")
def rookie():
    return pd.read_parquet(ARP.ROOKIE_MATRIX, columns=list(ARP.ROOKIE_MATRIX_COLUMNS))


@pytest.fixture(scope="module")
def composed():
    return ARP.authorized_composed_feature_reader()()


# =====================================================================================================
# 1. Exact key-set equality, and the frozen QB exclusion
# =====================================================================================================
def test_the_rookie_key_set_EQUALS_the_routed_spine_rows_exactly(spine, rookie):
    routed = spine[(spine["is_rookie"].astype(int) == 1)
                   & spine["position"].isin(ARP.ROOKIE_MATRIX_POSITIONS)]
    assert len(routed) == EXPECTED_ROOKIE_ROWS == len(rookie)
    assert set(map(tuple, routed[KEYS].to_numpy())) == set(map(tuple, rookie[KEYS].to_numpy()))
    assert not rookie.duplicated(subset=KEYS).any()


def test_the_QB_rookie_exclusion_is_PRESERVED_exactly(spine, rookie):
    """QB/rookie is not in SHIPPED_ARM0_BUCKETS — the arm was HELD. Those rows exist on the spine and
    must NOT be in the rookie matrix; the composed frame keeps them on veteran-source values."""
    qb_rookie = spine[(spine["is_rookie"].astype(int) == 1) & (spine["position"] == "QB")]
    assert len(qb_rookie) == EXPECTED_QB_ROOKIE_ROWS
    assert not (set(map(tuple, qb_rookie[KEYS].to_numpy()))
                & set(map(tuple, rookie[KEYS].to_numpy())))
    assert ("QB", "rookie") not in ARP.SHIPPED_ARM0_BUCKETS
    assert ("QB", "rookie") in EX.MISSING_BUNDLES


def test_the_composed_frame_preserves_the_spine_row_count_and_ORDER(spine, composed):
    assert len(composed) == len(spine) == EXPECTED_SPINE_ROWS
    pd.testing.assert_frame_equal(composed[KEYS].reset_index(drop=True),
                                  spine[KEYS].reset_index(drop=True))


# =====================================================================================================
# 2. All seven buckets feedable, with complete ordered features
# =====================================================================================================
def test_all_seven_shipped_buckets_have_rows_and_COMPLETE_ordered_features(composed):
    is_rookie = composed["is_rookie"].astype(int) == 1
    assert len(ARP.SHIPPED_ARM0_BUCKETS) == 7
    for (pos, bucket) in ARP.SHIPPED_ARM0_BUCKETS:
        rows = composed[(composed["position"] == pos) & (is_rookie == (bucket == "rookie"))]
        assert len(rows) == EXPECTED_BUCKET_ROWS[(pos, bucket)] > 0
        fc = ARP.bundle_feature_cols(pos, bucket)
        assert not [c for c in fc if c not in composed.columns], f"{pos}/{bucket} missing features"
        # selected in the bundle's EXACT order
        assert tuple(rows[list(fc)].columns) == tuple(fc)
        assert tuple(fc) == tuple(PINS.BUNDLE_FEATURE_PINS[(pos, bucket)]["feature_cols"])


def test_panel_bucket_gaps_is_EMPTY_on_the_composed_frame(composed):
    assert ARP.union_bucket_gaps(composed) == []


def test_the_gap_check_is_NOT_weakened(composed):
    """RED control: drop one required feature and the check must still fire."""
    broken = composed.drop(columns=["pff_receiving_yprr"])
    gaps = ARP.union_bucket_gaps(broken)
    assert gaps and any("rookie" in g for g in gaps)


def test_every_bucket_row_has_at_least_one_non_null_required_feature(composed):
    """No bucket is 'present' only as all-NULL rows."""
    is_rookie = composed["is_rookie"].astype(int) == 1
    for (pos, bucket) in ARP.SHIPPED_ARM0_BUCKETS:
        rows = composed[(composed["position"] == pos) & (is_rookie == (bucket == "rookie"))]
        fc = list(ARP.bundle_feature_cols(pos, bucket))
        assert int(rows[fc].notna().any(axis=1).sum()) == len(rows)


# =====================================================================================================
# 3. Source ownership — veteran identical, rookie authoritative even when NULL
# =====================================================================================================
def test_VETERAN_rows_are_value_identical_to_the_veteran_source(spine, composed):
    is_rookie = composed["is_rookie"].astype(int) == 1
    routed = is_rookie & composed["position"].isin(ARP.ROOKIE_MATRIX_POSITIONS)
    vet_rows = ~routed
    for c in ARP.VETERAN_FEATURE_COLUMNS:
        a, b = spine.loc[vet_rows.to_numpy(), c], composed.loc[vet_rows, c]
        if pd.api.types.is_numeric_dtype(a):
            assert np.allclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float),
                               rtol=0, atol=0, equal_nan=True), f"{c} changed on a veteran row"
        else:
            assert list(a.astype(str)) == list(b.astype(str)), f"{c} changed on a veteran row"


def test_QB_rookie_rows_keep_VETERAN_source_values(spine, composed):
    m = (composed["is_rookie"].astype(int) == 1) & (composed["position"] == "QB")
    assert int(m.sum()) == EXPECTED_QB_ROOKIE_ROWS
    for c in ARP.SHARED_SOURCE_COLUMNS:
        a = spine.loc[m.to_numpy(), c].to_numpy(dtype=float)
        b = composed.loc[m, c].to_numpy(dtype=float)
        assert np.allclose(a, b, rtol=0, atol=0, equal_nan=True), f"{c} moved on a QB rookie row"


def test_ROOKIE_rows_take_the_ROOKIE_value_for_every_shared_column(rookie, composed):
    """The nine overlapping columns must come from the rookie matrix on rookie rows."""
    assert len(ARP.SHARED_SOURCE_COLUMNS) == 9
    ref = rookie.set_index(KEYS)
    sub = composed[(composed["is_rookie"].astype(int) == 1)
                   & composed["position"].isin(ARP.ROOKIE_MATRIX_POSITIONS)].set_index(KEYS)
    for c in ARP.SHARED_SOURCE_COLUMNS:
        a = ref.loc[sub.index, c].to_numpy(dtype=float)
        b = sub[c].to_numpy(dtype=float)
        assert np.allclose(a, b, rtol=0, atol=0, equal_nan=True), f"{c} did not come from the rookie source"


def test_an_intentional_rookie_NULL_is_NOT_backfilled_from_the_veteran_source(spine, rookie):
    """The decisive no-coalesce property, on a CONSTRUCTED case so it cannot be vacuous."""
    r = rookie.copy()
    col = "age"                                     # shared by both sources
    assert col in ARP.SHARED_SOURCE_COLUMNS
    r.loc[r.index[:5], col] = np.nan                # deliberately NULL in the rookie source
    key0 = tuple(r.loc[r.index[0], KEYS])
    spine_val = spine.set_index(KEYS).loc[key0, col]
    assert pd.notna(spine_val), "the spine must have a value, or the test proves nothing"

    frame = ARP.compose_feature_frame(spine, r)
    got = frame.set_index(KEYS).loc[key0, col]
    assert pd.isna(got), "an intentional rookie NULL was back-filled from the veteran source"


def test_a_DIFFERING_shared_value_resolves_to_the_rookie_source(spine, rookie):
    r = rookie.copy()
    col = "prior_team_plays"
    r.loc[r.index[0], col] = -12345.0
    key0 = tuple(r.loc[r.index[0], KEYS])
    frame = ARP.compose_feature_frame(spine, r)
    assert frame.set_index(KEYS).loc[key0, col] == -12345.0


def test_identity_and_routing_fields_AGREE_between_the_sources(spine, rookie):
    ref = rookie.set_index(KEYS)
    sub = spine[(spine["is_rookie"].astype(int) == 1)
                & spine["position"].isin(ARP.ROOKIE_MATRIX_POSITIONS)].set_index(KEYS)
    assert list(ref.loc[sub.index, "position"]) == list(sub["position"])
    assert (ref.loc[sub.index, "is_rookie"].astype(int) == 1).all()
    assert list(ref.loc[sub.index, "norm_name"].astype(str)) == list(sub["norm_name"].astype(str))


# =====================================================================================================
# 4. Refusals — missing, extra, duplicate, misrouted, mismatched
# =====================================================================================================
def test_a_MISSING_rookie_row_refuses(spine, rookie):
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.compose_feature_frame(spine, rookie.iloc[1:].reset_index(drop=True))
    assert "no rookie-matrix row" in str(e.value)


def test_an_EXTRA_rookie_row_refuses(spine, rookie):
    extra = rookie.iloc[[0]].copy()
    extra[ARP.PLAYER_KEY] = "00-9999999"
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.compose_feature_frame(spine, pd.concat([rookie, extra], ignore_index=True))
    assert "match no routed spine row" in str(e.value)


def test_a_DUPLICATE_rookie_row_refuses(spine, rookie):
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.compose_feature_frame(spine, pd.concat([rookie, rookie.iloc[[0]]], ignore_index=True))
    assert "duplicate" in str(e.value)


def test_a_POSITION_mismatched_rookie_row_refuses(spine, rookie):
    r = rookie.copy()
    r.loc[r.index[0], "position"] = "QB" if r.loc[r.index[0], "position"] != "QB" else "RB"
    with pytest.raises(ARP.AssemblyError):
        ARP.compose_feature_frame(spine, r)


def test_a_SEASON_mismatched_rookie_row_refuses(spine, rookie):
    r = rookie.copy()
    r.loc[r.index[0], ARP.SEASON_KEY] = 2099
    with pytest.raises(ARP.AssemblyError):
        ARP.compose_feature_frame(spine, r)


def test_a_MISROUTED_rookie_row_refuses(spine, rookie):
    """is_rookie == 0 in the rookie matrix means the routing disagrees."""
    r = rookie.copy()
    r.loc[r.index[0], "is_rookie"] = 0
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.compose_feature_frame(spine, r)
    assert "is_rookie" in str(e.value)


def test_a_QB_rookie_row_in_the_rookie_matrix_refuses(spine, rookie):
    """The frozen exclusion, enforced rather than assumed."""
    qb = spine[(spine["is_rookie"].astype(int) == 1) & (spine["position"] == "QB")].iloc[[0]]
    row = rookie.iloc[[0]].copy()
    row[ARP.PLAYER_KEY] = qb[ARP.PLAYER_KEY].iloc[0]
    row[ARP.SEASON_KEY] = qb[ARP.SEASON_KEY].iloc[0]
    row["position"] = "QB"
    with pytest.raises(ARP.AssemblyError):
        ARP.compose_feature_frame(spine, pd.concat([rookie, row], ignore_index=True))


def test_REORDERING_the_rookie_rows_changes_nothing(spine, rookie):
    """The join is on keys, so order is irrelevant — but the SPINE order must still be preserved."""
    a = ARP.compose_feature_frame(spine, rookie)
    b = ARP.compose_feature_frame(spine, rookie.iloc[::-1].reset_index(drop=True))
    pd.testing.assert_frame_equal(a, b)


def test_no_silent_row_or_bucket_loss(spine, composed):
    assert len(composed) == len(spine)
    is_rookie = composed["is_rookie"].astype(int) == 1
    total = sum(len(composed[(composed["position"] == p) & (is_rookie == (b == "rookie"))])
                for p, b in ARP.SHIPPED_ARM0_BUCKETS)
    assert total + EXPECTED_QB_ROOKIE_ROWS == EXPECTED_SPINE_ROWS


# =====================================================================================================
# 5. Schema, provenance, and no outcome/market leakage
# =====================================================================================================
def test_the_union_schema_is_exact_and_derived(composed):
    assert list(composed.columns) == list(ARP.FROZEN_UNION_FEATURE_COLUMNS)
    assert len(ARP.FROZEN_UNION_FEATURE_COLUMNS) == 87 == (
        len(ARP.VETERAN_FEATURE_COLUMNS) + len(ARP.ROOKIE_ONLY_FEATURE_COLUMNS)
        + len(ARP.ROOKIE_MATRIX_PROVENANCE))
    assert len(ARP.ROOKIE_ONLY_FEATURE_COLUMNS) == 45 and len(ARP.SHARED_SOURCE_COLUMNS) == 9


def test_no_outcome_target_weight_or_market_field_is_in_the_frame(composed):
    assert not (set(composed.columns) & ARP.FORBIDDEN_IN_FEATURES)


@pytest.mark.parametrize("token", ["target_ppg", "target_games", "sample_weight", "adp_", "sleeper",
                                   "season_total", "fantasy_points", "outcome"])
def test_no_column_name_carries_an_outcome_or_market_token(composed, token):
    assert not [c for c in composed.columns if token in c.lower()]


def test_PROVENANCE_columns_never_enter_a_model_feature_list(composed):
    for (pos, bucket) in ARP.SHIPPED_ARM0_BUCKETS:
        fc = set(ARP.bundle_feature_cols(pos, bucket))
        assert not (fc & set(ARP.NON_MODEL_HELPER_COLUMNS)), f"{pos}/{bucket} names a provenance column"
    assert set(ARP.NON_MODEL_HELPER_COLUMNS) == set(ARP.ROOKIE_MATRIX_PROVENANCE)
    assert not (set(ARP.panel_feature_columns(composed.assign(y=0.0, outcome_state="x", bucket="v")))
                & set(ARP.FORBIDDEN_IN_FEATURES))


def test_the_provenance_columns_are_PRESENT_and_still_point_in_time(composed):
    for c in ARP.ROOKIE_MATRIX_PROVENANCE:
        assert c in composed.columns
        nn = composed[c].notna()
        assert int(nn.sum()) > 0
        assert int((composed.loc[nn, ARP.SEASON_KEY] - composed.loc[nn, c]).min()) >= 1


# =====================================================================================================
# 6. Both hashes verified before either frame is accepted
# =====================================================================================================
def test_BOTH_source_hashes_are_verified_before_acceptance(monkeypatch):
    seen = []
    real_v, real_r = ARP.verify_veteran_snapshot_provenance, ARP.verify_rookie_matrix_provenance
    monkeypatch.setattr(ARP, "verify_veteran_snapshot_provenance",
                        lambda *a, **k: seen.append("veteran") or real_v(*a, **k))
    monkeypatch.setattr(ARP, "verify_rookie_matrix_provenance",
                        lambda *a, **k: seen.append("rookie") or real_r(*a, **k))
    ARP.authorized_composed_feature_reader()()
    assert seen == ["veteran", "rookie"]


@pytest.mark.parametrize("attr", ["VETERAN_SNAPSHOT_SHA256", "ROOKIE_MATRIX_SHA256"])
def test_either_drifted_source_hash_refuses(monkeypatch, attr):
    monkeypatch.setattr(ARP, attr, "0" * 64)
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.authorized_composed_feature_reader()()
    assert "sha256" in str(e.value)


def test_constructing_the_composed_reader_reads_nothing(tmp_path):
    reader = ARP.authorized_composed_feature_reader(veteran_path=tmp_path / "nope.parquet")
    with pytest.raises(ARP.AssemblyError):
        reader()


# =====================================================================================================
# 7. Authorization — zero readers in every non-authorized state
# =====================================================================================================
@pytest.mark.parametrize("constant_open,env_open", [(False, False), (True, False), (False, True)])
def test_every_closed_or_PARTIAL_state_reaches_zero_readers(monkeypatch, constant_open, env_open):
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", constant_open, raising=False)
    if env_open:
        monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    else:
        monkeypatch.delenv(EX.REAL_FIT_ENV_SWITCH, raising=False)
    reads = []
    monkeypatch.setattr(ARP, "authorized_composed_feature_reader",
                        lambda *a, **k: reads.append("features") or (lambda: None))
    monkeypatch.setattr(ARP, "authorized_outcome_reader",
                        lambda *a, **k: reads.append("outcome") or (lambda: None))
    with pytest.raises(RuntimeError):
        EX.run_authorized_real((2024,), 10, 2, verbose=False)
    assert reads == []


def test_the_authorized_path_uses_the_COMPOSED_reader():
    import inspect
    src = inspect.getsource(EX.run_authorized_real)
    assert "authorized_composed_feature_reader" in src


def test_the_synthetic_mode_never_reaches_a_reader(monkeypatch):
    reads = []
    monkeypatch.setattr(ARP, "authorized_composed_feature_reader",
                        lambda *a, **k: reads.append("features") or (lambda: None))
    monkeypatch.setattr(sys, "argv", ["prog", "--run-mode", "synthetic_prefit"])
    EX.main()
    assert reads == []


# =====================================================================================================
# 8. Synthetic end-to-end: adapter -> experiment -> temp writer, no real outcome
# =====================================================================================================
def test_SYNTHETIC_end_to_end_through_adapter_experiment_and_writer(tmp_path, composed):
    """An authorized-SHAPED fixture: the real composed FEATURES with a SYNTHETIC target.

    No lock is opened and the real outcome reader never runs — `y` is generated here.
    """
    rng = np.random.default_rng(5)
    # the FULL composed frame: the union schema is accepted only when all seven buckets are feedable,
    # so a subset would (correctly) be refused. Only the TARGET is synthetic.
    # the CANONICAL pre-outcome eligibility rule, not an ad-hoc filter
    eligible, acc = ARP.evaluation_eligibility(composed)
    assert acc["eligible_evaluation_population"] == 7153
    outcomes = eligible[KEYS].copy()
    outcomes[ARP.OUTCOME_COLUMN] = rng.normal(150, 30, size=len(eligible)).round(3)
    fake_assembled = ARP.assemble_panel_core(eligible, outcomes)
    panel, report = ARP.panel_for_experiment(fake_assembled)          # full bucket coverage REQUIRED
    assert report["n_rows"] == len(eligible) == 7153
    assert set(panel["bucket"]) == {"veteran", "rookie"}
    assert ARP.panel_bucket_gaps(panel) == []

    coach_a = pd.read_csv(EX.DATA / "team_coach_features_design_a_v39.csv")
    coach_b = pd.read_csv(EX.DATA / "team_coach_features_design_b_oracle_v39.csv")
    # The eligibility amendment (v3.9u) already removed the 80 null-team rows and the 117 QB/rookie
    # rows, so the panel satisfies the no-implicit-loss invariant by construction.
    EX.assert_no_implicit_row_loss(panel)      # the eligible panel already satisfies the invariant
    EX.reset_pipeline_assertions()
    frames = EX.run_experiment(panel, coach_a, coach_b, outer_seasons=[2020], positions=["RB"],
                               bootstrap_draws=20, run_placebo=True, placebo_draws=3, verbose=False)
    hashes = WR.write_results(frames, out_dir=tmp_path)
    assert sorted(hashes) == sorted(WR.RESULT_FILES)
    assert EX.real_fit_lock_state() == (False, False)


def test_the_end_to_end_never_touched_the_canonical_outcome_snapshot():
    """The weekly snapshot is not opened by this module at all."""
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    needle = "player" + "_stats_" + "2011_2025"
    assert needle not in src.replace('needle = "player" + "_stats_" + "2011_2025"', "")


def test_the_stop_state_is_unchanged():
    pf = EX.preflight(pipeline_assertions={k: 3 for k in EX._PIPELINE_ASSERTIONS})
    assert pf["all_ok"] is True and pf["n_checks"] == 21
    assert ARP.activation_readiness()[0] is True
    assert ARP.authorized_real_gate(pf)[0] is False
    assert EX.real_fit_lock_state() == (False, False)
    assert not (WR.RESULTS.exists() and list(WR.RESULTS.glob("*_v39.csv")))


def test_the_null_team_rows_are_MEASURED_not_assumed(composed, spine):
    """80 panel rows carry NO team, so they can receive no coaching feature under any arm.

    They come from the veteran SOURCE — composition does not introduce them — and every non-null
    (season, team) pair IS covered by the Design A coaching table. Recorded here so the number cannot
    drift silently; whether to exclude them from the real run is a POPULATION decision, not a test's.
    """
    null_team = composed["team"].isna()
    assert int(null_team.sum()) == 80
    assert int(spine["team"].isna().sum()) == 80, "composition introduced null teams"
    assert (composed.loc[null_team, "is_rookie"].astype(int) == 0).all(), (
        "a rookie-bucket row lost its team")

    coach_a = pd.read_csv(EX.DATA / "team_coach_features_design_a_v39.csv")
    covered = set(map(tuple, coach_a[["season", "team"]].drop_duplicates().to_numpy()))
    have_team = composed[composed["team"].notna()]
    uncovered = [(int(s), t) for s, t in zip(have_team["season"], have_team["team"])
                 if (int(s), t) not in covered]
    assert not uncovered, f"{len(uncovered)} row(s) have a team with no coaching bundle"
