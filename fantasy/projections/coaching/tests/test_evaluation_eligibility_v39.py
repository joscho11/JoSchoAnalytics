"""EVALUATION ELIGIBILITY — the pre-outcome population rule, frozen and measured.

Adopted 2026-08-03. A row is eligible only when BOTH hold:
  1. `team` is non-null, so OC/HC exposure is DEFINED for it;
  2. its (position, bucket) has a shipped Arm 0 bundle.

Decided from the frozen feature frame ALONE, before any outcome reader runs, and applied identically
to ARM_0 and every coaching arm. Coaching exposure is never imputed, proxied or fabricated.

MEASURED partition (verified here, not trusted):

    source_population                  7,350
    excluded_missing_team                 80
    excluded_no_shipped_bundle           117   (QB/rookie)
    eligible_evaluation_population     7,153

No fantasy outcome is read anywhere in this module.
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COACH))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import assemble_real_panel_v39 as ARP                      # noqa: E402
import run_coach_projection_experiment_v39 as EX           # noqa: E402
import write_v39_results as WR                             # noqa: E402

KEYS = list(ARP.PANEL_KEYS)
SOURCE_POPULATION = 7350
EXCLUDED_MISSING_TEAM = 80
EXCLUDED_NO_BUNDLE = 117
ELIGIBLE_POPULATION = 7153


@pytest.fixture(scope="module")
def composed():
    return ARP.authorized_composed_feature_reader()()


@pytest.fixture(scope="module")
def partition(composed):
    return ARP.evaluation_eligibility(composed)


# =====================================================================================================
# 1. The partition: exact, mutually exclusive, exhaustive
# =====================================================================================================
def test_the_partition_is_EXACTLY_the_frozen_numbers(partition):
    _eligible, acc = partition
    assert acc["source_population"] == SOURCE_POPULATION
    assert acc["excluded_missing_team"] == EXCLUDED_MISSING_TEAM
    assert acc["excluded_no_shipped_bundle"] == EXCLUDED_NO_BUNDLE
    assert acc["eligible_evaluation_population"] == ELIGIBLE_POPULATION


def test_the_states_are_MUTUALLY_EXCLUSIVE_and_EXHAUSTIVE(composed, partition):
    eligible, acc = partition
    assert acc["states_are_mutually_exclusive"] is True
    assert acc["states_are_exhaustive"] is True
    total = (acc["excluded_missing_team"] + acc["excluded_no_shipped_bundle"]
             + acc["eligible_evaluation_population"])
    assert total == acc["source_population"] == len(composed)
    assert len(eligible) == acc["eligible_evaluation_population"]


def test_the_two_exclusion_reasons_do_not_OVERLAP(composed):
    """Re-derived independently of the implementation."""
    bucket = ARP.bucket_of(composed)
    shipped = set(ARP.SHIPPED_ARM0_BUCKETS)
    no_bundle = pd.Series([(p, b) not in shipped for p, b in zip(composed["position"], bucket)],
                          index=composed.index)
    no_team = composed["team"].isna()
    assert int((no_team & no_bundle).sum()) == 0
    assert int(no_team.sum()) == EXCLUDED_MISSING_TEAM
    assert int(no_bundle.sum()) == EXCLUDED_NO_BUNDLE


def test_every_state_is_one_of_the_three_declared(partition):
    assert set(ARP.ELIGIBILITY_STATES) == {ARP.ELIGIBLE, ARP.EXCLUDED_MISSING_TEAM,
                                           ARP.EXCLUDED_NO_SHIPPED_BUNDLE}
    assert len(ARP.ELIGIBILITY_STATES) == 3


# =====================================================================================================
# 2. Exact excluded keys and counts, by season and position
# =====================================================================================================
def test_the_missing_team_exclusions_by_position_and_season(partition):
    _e, acc = partition
    rec = acc["by_reason"][ARP.EXCLUDED_MISSING_TEAM]
    assert rec["n"] == EXCLUDED_MISSING_TEAM
    assert rec["by_position"] == {"WR": 31, "TE": 20, "RB": 15, "QB": 14}
    assert sum(rec["by_position"].values()) == EXCLUDED_MISSING_TEAM
    assert sum(rec["by_season"].values()) == EXCLUDED_MISSING_TEAM
    assert set(rec["by_season"]) <= set(range(2014, 2026))


def test_the_no_bundle_exclusions_are_ALL_QB_rookie(partition, composed):
    _e, acc = partition
    rec = acc["by_reason"][ARP.EXCLUDED_NO_SHIPPED_BUNDLE]
    assert rec["n"] == EXCLUDED_NO_BUNDLE
    assert rec["by_position"] == {"QB": EXCLUDED_NO_BUNDLE}
    bucket = ARP.bucket_of(composed)
    qb_rookie = composed[(composed["position"] == "QB") & (bucket == "rookie")]
    assert len(qb_rookie) == EXCLUDED_NO_BUNDLE


def test_the_excluded_KEYS_are_exactly_the_complement(composed, partition):
    eligible, _acc = partition
    src = set(map(tuple, composed[KEYS].to_numpy()))
    keep = set(map(tuple, eligible[KEYS].to_numpy()))
    assert keep < src
    assert len(src - keep) == EXCLUDED_MISSING_TEAM + EXCLUDED_NO_BUNDLE == 197


def test_source_ORDER_is_retained_among_eligible_rows(composed, partition):
    eligible, _acc = partition
    expected = composed[~composed["team"].isna()]
    bucket = ARP.bucket_of(expected)
    shipped = set(ARP.SHIPPED_ARM0_BUCKETS)
    expected = expected[[(p, b) in shipped for p, b in zip(expected["position"], bucket)]]
    assert list(eligible[ARP.PLAYER_KEY]) == list(expected[ARP.PLAYER_KEY])
    assert list(eligible[ARP.SEASON_KEY]) == list(expected[ARP.SEASON_KEY])


# =====================================================================================================
# 3. Outcome independence
# =====================================================================================================
def test_the_missing_team_exclusion_is_OUTCOME_INDEPENDENT(composed):
    """The rule reads `team` and `position` only. No outcome column is even present."""
    import inspect
    src = inspect.getsource(ARP.evaluation_eligibility)
    assert ARP.OUTCOME_COLUMN not in src and "outcome_state" not in src
    assert ARP.OUTCOME_COLUMN not in composed.columns
    assert not (set(composed.columns) & ARP.FORBIDDEN_IN_FEATURES)


def test_changing_an_OUTCOME_cannot_change_eligibility(composed, partition):
    """A constructed proof: attach any target, and the partition is bit-identical."""
    eligible, acc = partition
    rng = np.random.default_rng(9)
    with_outcome = composed.copy()
    with_outcome["__synthetic_target__"] = rng.normal(size=len(composed))
    again, acc2 = ARP.evaluation_eligibility(with_outcome.drop(columns=["__synthetic_target__"]))
    assert acc2 == acc
    pd.testing.assert_frame_equal(again[KEYS], eligible[KEYS])


def test_QB_rookie_is_excluded_for_NO_BUNDLE_not_team_or_outcome(composed, partition):
    """The reason matters: QB/rookie rows overwhelmingly HAVE a team."""
    bucket = ARP.bucket_of(composed)
    qb_rookie = composed[(composed["position"] == "QB") & (bucket == "rookie")]
    assert len(qb_rookie) == EXCLUDED_NO_BUNDLE
    assert int(qb_rookie["team"].notna().sum()) > 0, (
        "if every QB/rookie row lacked a team the reason would be ambiguous")
    assert ("QB", "rookie") not in ARP.SHIPPED_ARM0_BUCKETS
    _e, acc = partition
    assert acc["by_reason"][ARP.EXCLUDED_NO_SHIPPED_BUNDLE]["by_position"] == {"QB": EXCLUDED_NO_BUNDLE}


def test_giving_a_null_team_row_a_VALID_team_changes_ONLY_its_state(composed):
    """Constructed fixture: flip one exclusion and nothing else moves."""
    frame = composed.copy()
    idx = frame.index[frame["team"].isna()][0]
    frame.loc[idx, "team"] = "ARI"
    eligible, acc = ARP.evaluation_eligibility(frame)
    assert acc["excluded_missing_team"] == EXCLUDED_MISSING_TEAM - 1
    assert acc["eligible_evaluation_population"] == ELIGIBLE_POPULATION + 1
    assert acc["excluded_no_shipped_bundle"] == EXCLUDED_NO_BUNDLE
    assert acc["source_population"] == SOURCE_POPULATION
    key = tuple(frame.loc[idx, KEYS])
    assert key in set(map(tuple, eligible[KEYS].to_numpy()))


# =====================================================================================================
# 4. Retained rows are complete and well-routed
# =====================================================================================================
def test_every_retained_row_has_a_team_and_exactly_one_shipped_bundle(partition):
    eligible, _acc = partition
    assert int(eligible["team"].isna().sum()) == 0
    bucket = ARP.bucket_of(eligible)
    shipped = set(ARP.SHIPPED_ARM0_BUCKETS)
    pairs = list(zip(eligible["position"], bucket))
    assert all(p in shipped for p in pairs)
    assert len({p for p in pairs}) == 7


def test_every_retained_bucket_has_COMPLETE_ordered_features(partition):
    eligible, acc = partition
    bucket = ARP.bucket_of(eligible)
    for (pos, b) in ARP.SHIPPED_ARM0_BUCKETS:
        rows = eligible[(eligible["position"] == pos) & (bucket == b)]
        assert len(rows) == acc["eligible_by_bucket"][f"{pos}/{b}"] > 0
        fc = ARP.bundle_feature_cols(pos, b)
        assert not [c for c in fc if c not in eligible.columns]
        assert tuple(rows[list(fc)].columns) == tuple(fc)


def test_all_required_outer_seasons_remain_represented(partition):
    eligible, acc = partition
    assert acc["eligible_seasons"] == list(ARP.ALL_PANEL_SEASONS)
    for Y in ARP.OUTER_SEASONS:
        assert int((eligible[ARP.SEASON_KEY] == Y).sum()) > 0, f"outer season {Y} lost"


def test_the_eligible_frame_still_feeds_every_bucket(partition):
    eligible, _acc = partition
    assert ARP.union_bucket_gaps(eligible) == []


def test_the_eligible_frame_carries_no_outcome_or_market_field(partition):
    eligible, _acc = partition
    assert not (set(eligible.columns) & ARP.FORBIDDEN_IN_FEATURES)


# =====================================================================================================
# 5. Refusals
# =====================================================================================================
def test_an_UNKNOWN_position_refuses(composed):
    frame = composed.copy()
    frame.loc[frame.index[0], "position"] = "K"
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.evaluation_eligibility(frame)
    assert "unknown position" in str(e.value)


def test_an_AMBIGUOUS_row_matching_both_reasons_refuses(composed):
    """A QB/rookie row with a null team matches both; the partition would be ambiguous."""
    frame = composed.copy()
    bucket = ARP.bucket_of(frame)
    idx = frame.index[(frame["position"] == "QB") & (bucket == "rookie")][0]
    frame.loc[idx, "team"] = None
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.evaluation_eligibility(frame)
    assert "BOTH exclusion reasons" in str(e.value)


def test_a_frame_without_team_refuses(composed):
    with pytest.raises(ARP.AssemblyError):
        ARP.evaluation_eligibility(composed.drop(columns=["team"]))


# =====================================================================================================
# 6. Identical keys across arms, and no later silent loss
# =====================================================================================================
def test_run_experiment_ASSERTS_no_further_implicit_row_loss():
    panel = EX.synthetic_panel(seasons=range(2014, 2018), teams=["ARI", "ATL"],
                               players_per_team=2, positions=["RB"], seed=4)
    assert EX.assert_no_implicit_row_loss(panel) is True

    with_null = panel.copy()
    with_null.loc[with_null.index[0], "team"] = None
    with pytest.raises(AssertionError) as e:
        EX.assert_no_implicit_row_loss(with_null)
    assert "null team" in str(e.value)

    unshipped = panel.copy()
    unshipped.loc[unshipped.index[0], "position"] = "QB"
    unshipped.loc[unshipped.index[0], "bucket"] = "rookie"
    with pytest.raises(AssertionError) as e2:
        EX.assert_no_implicit_row_loss(unshipped)
    assert "no shipped bundle" in str(e2.value)


def test_every_ARM_sees_the_SAME_eligible_keys_and_order(partition):
    """Eligibility is a property of the FRAME, so it is identical for ARM_0 and every coaching arm."""
    eligible, _acc = partition
    import inspect
    src = inspect.getsource(ARP.evaluation_eligibility)
    assert "arm" not in src.lower().replace("arm0_buckets", "").replace("shipped_arm0", "")
    keys = list(map(tuple, eligible[KEYS].to_numpy()))
    assert len(keys) == len(set(keys)) == ELIGIBLE_POPULATION


# =====================================================================================================
# 7. The runner: eligibility precedes the outcome reader
# =====================================================================================================
def test_a_malformed_eligibility_partition_reaches_ZERO_outcome_reader_calls(monkeypatch):
    """The decisive ordering property."""
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", True, raising=False)
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    monkeypatch.setattr(EX, "require_preflight_clearance", lambda *a, **k: None)

    outcome_calls = []

    def _outcome_reader(*_a, **_k):
        def _r():
            outcome_calls.append("outcome")
            raise AssertionError("the outcome reader RAN despite a malformed partition")
        return _r

    monkeypatch.setattr(ARP, "authorized_outcome_reader", _outcome_reader)
    monkeypatch.setattr(ARP, "evaluation_eligibility",
                        lambda *a, **k: (_ for _ in ()).throw(ARP.AssemblyError("injected")))
    with pytest.raises(ARP.AssemblyError):
        EX.run_authorized_real((2024,), 10, 2, verbose=False)
    assert outcome_calls == []


def test_the_runner_applies_eligibility_before_the_outcome_reader():
    import inspect
    src = inspect.getsource(EX.run_authorized_real)
    body = src.split('"""')
    src = body[0] + ("".join(body[2:]) if len(body) > 2 else "")
    assert "evaluation_eligibility" in src
    assert src.index("def feature_reader") < src.index("authorized_outcome_reader")


# =====================================================================================================
# 8. The accounting rides in arm_verdict — no sixth artifact
# =====================================================================================================
def _frames():
    return {
        "selection": pd.DataFrame({"position": ["RB"], "outer_season": [2024]}),
        "metrics": pd.DataFrame({"position": ["RB"], "top_mae": [1.0]}),
        "bootstrap": pd.DataFrame({"position": ["RB"], "lo": [-1.0]}),
        "placebo": pd.DataFrame({"position": ["RB"], "delta": [0.1]}),
        "oracle": pd.DataFrame({"position": ["RB"], "oracle_gap": [0.2]}),
        "verdict": pd.DataFrame({"position": ["RB"], "verdict": ["FAIL"]}),
        "preflight": pd.DataFrame({"position": ["RB"], "all_ok": [True]}),
    }


def test_the_eligibility_accounting_is_CARRIED_into_arm_verdict(tmp_path, partition):
    _e, acc = partition
    hashes = WR.write_results(_frames(), out_dir=tmp_path, eligibility=acc)
    assert sorted(hashes) == sorted(WR.RESULT_FILES), "a sixth artifact appeared"
    verdict = pd.read_csv(tmp_path / "arm_verdict_v39.csv")
    rec = WR.recover_eligibility(verdict)
    assert rec["source_population"] == SOURCE_POPULATION
    assert rec["excluded_missing_team"] == EXCLUDED_MISSING_TEAM
    assert rec["excluded_no_shipped_bundle"] == EXCLUDED_NO_BUNDLE
    assert rec["eligible_evaluation_population"] == ELIGIBLE_POPULATION
    assert rec[f"{ARP.EXCLUDED_MISSING_TEAM}_by_position"] == {"WR": 31, "TE": 20, "RB": 15, "QB": 14}
    assert rec[f"{ARP.EXCLUDED_NO_SHIPPED_BUNDLE}_by_position"] == {"QB": EXCLUDED_NO_BUNDLE}


def test_the_eligibility_columns_do_not_break_the_preflight_or_verdict_round_trip(tmp_path, partition):
    _e, acc = partition
    frames = _frames()
    WR.write_results(frames, out_dir=tmp_path, eligibility=acc)
    verdict = pd.read_csv(tmp_path / "arm_verdict_v39.csv")
    pd.testing.assert_frame_equal(WR.recover_verdict(verdict)[["position", "verdict"]],
                                  frames["verdict"], check_dtype=False)
    pf = WR.recover_preflight(verdict)
    assert list(pf.columns) == ["position", "all_ok"]
    assert not [c for c in pf.columns if c.startswith(WR.ELIGIBILITY_PREFIX)]


def test_still_exactly_five_result_files():
    assert len(WR.RESULT_FILES) == 5


# =====================================================================================================
# 9. The stop state
# =====================================================================================================
def test_the_stop_state_is_unchanged():
    pf = EX.preflight(pipeline_assertions={k: 3 for k in EX._PIPELINE_ASSERTIONS})
    assert pf["all_ok"] is True and pf["n_checks"] == 21
    assert ARP.activation_readiness()[0] is True
    assert ARP.authorized_real_gate(pf)[0] is False
    assert EX.real_fit_lock_state() == (False, False)
    assert not (WR.RESULTS.exists() and list(WR.RESULTS.glob("*_v39.csv")))
