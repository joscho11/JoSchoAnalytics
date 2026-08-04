"""THE AUTHORIZED-REAL RUNNER — result ownership, the panel adapter, the CLI, and the 5-file mapping.

Approved 2026-08-03 as a pre-outcome OPERATIONAL amendment (Option A): the five preregistered result
files move from `coaching/data/` to `coaching/results/`, because the preflight check
`no_unauthorized_v39_artifact` requires the `*_v39.*` set in `data/` to equal exactly the five FEATURE
artifacts. That check and `V39_ARTIFACT_HASHES` are UNCHANGED. Storage moved; the experiment did not.

NOTHING HERE OPENS A LOCK, READS A REAL OUTCOME, FITS A REAL MODEL OR WRITES A REAL RESULT. Every
fixture is synthetic or a temp directory written by the test itself.
"""
import hashlib
import pathlib
import shutil
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


# =====================================================================================================
# Synthetic frames
# =====================================================================================================
def synth_frames(seed=3):
    """Seven frames shaped like `run_experiment`'s return, with distinctive values."""
    rng = np.random.default_rng(seed)
    return {
        "selection": pd.DataFrame({"position": ["RB", "WR"], "outer_season": [2024, 2024],
                                   "selected_arm": ["ARM_0", "ARM_1"]}),
        "metrics": pd.DataFrame({"position": ["RB", "WR"], "arm": ["ARM_0", "ARM_1"],
                                 "top_mae": rng.normal(size=2), "full_mae": rng.normal(size=2)}),
        "bootstrap": pd.DataFrame({"position": ["RB"], "lo": [-1.0], "hi": [2.0]}),
        "placebo": pd.DataFrame({"position": ["RB"], "draw": [1], "delta": [0.5]}),
        "oracle": pd.DataFrame({"position": ["RB", "WR"], "oracle_gap": [0.25, 0.75],
                                "oracle_note": ["design_b", "design_b"]}),
        "verdict": pd.DataFrame({"position": ["RB", "WR"], "verdict": ["FAIL", "FAIL"]}),
        "preflight": pd.DataFrame({"position": ["RB", "WR"], "all_ok": [True, True],
                                   "n_checks": [21, 21]}),
    }


def synth_features(seasons=ARP.ALL_PANEL_SEASONS, players=3, seed=11):
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for i in range(players):
            r = {c: float(rng.normal()) for c in ARP.ARM0_VETERAN_FEATURES}
            r.update({ARP.PLAYER_KEY: f"00-{i:07d}", "player": f"P{i}", "norm_name": f"p{i}",
                      "position": "RB", "team": "ARI", ARP.SEASON_KEY: int(s),
                      "reconstructed": 0, "is_rookie": 0})
            rows.append(r)
    return pd.DataFrame(rows)[list(ARP.VETERAN_FEATURE_COLUMNS)]


def synth_outcomes(features, seed=12):
    """A SYNTHETIC target, in the reader's OWN schema.

    `outcome_state` is added by `assemble_panel_core`, not by the reader — `validate_outcome_frame`
    demands exactly the three key/target columns, so including it here would be wrong.
    """
    rng = np.random.default_rng(seed)
    out = features[list(ARP.PANEL_KEYS)].copy()
    out[ARP.OUTCOME_COLUMN] = rng.normal(150, 30, size=len(out)).round(3)
    return out


def assembled(features=None, outcomes=None):
    f = synth_features() if features is None else features
    o = synth_outcomes(f) if outcomes is None else outcomes
    return ARP.assemble_panel_core(f, o)


# =====================================================================================================
# 1. RESULT OWNERSHIP — data/ refuses, results/ is the home
# =====================================================================================================
def test_RED_result_files_in_the_DATA_dir_fail_the_existing_check(tmp_path):
    """The reason the paths moved, reproduced. Canonical data is never touched."""
    d = tmp_path / "data"
    shutil.copytree(EX.DATA, d)
    ran = {k: 3 for k in EX._PIPELINE_ASSERTIONS}
    before = EX.preflight(pipeline_assertions=ran, data_dir=d)
    assert before["all_ok"] is True and before["n_failed"] == 0

    for name in WR.RESULT_FILES:
        (d / name).write_text("placeholder\n", encoding="utf-8")
    after = EX.preflight(pipeline_assertions=ran, data_dir=d)
    assert after["all_ok"] is False
    assert "no_unauthorized_v39_artifact" in after["failures"]
    assert after["n_checks"] - after["n_failed"] == 20


def test_GREEN_results_in_the_RESULTS_dir_leave_the_data_check_untouched(tmp_path):
    d = tmp_path / "data"
    shutil.copytree(EX.DATA, d)
    hashes = WR.write_results(synth_frames(), out_dir=tmp_path / "results")
    assert sorted(hashes) == sorted(WR.RESULT_FILES)
    ran = {k: 3 for k in EX._PIPELINE_ASSERTIONS}
    pf = EX.preflight(pipeline_assertions=ran, data_dir=d)
    assert pf["all_ok"] is True and pf["n_failed"] == 0


def test_the_input_artifact_gate_is_UNCHANGED():
    """`V39_ARTIFACT_HASHES` still names exactly the five FEATURE artifacts, and no result name."""
    assert len(EX.V39_ARTIFACT_HASHES) == 5
    assert not (set(EX.V39_ARTIFACT_HASHES) & set(WR.RESULT_FILES))
    assert set(EX.V39_ARTIFACT_HASHES) == {
        "team_coach_features_design_a_v39.csv", "team_coach_features_design_b_oracle_v39.csv",
        "arm_feature_manifest_v39.json", "arm_feature_coverage_v39.csv",
        "arm_feature_lineage_v39.csv"}


def test_the_five_result_names_are_exactly_the_preregistered_ones():
    assert WR.RESULT_FILES == ("arm_selection_v39.csv", "arm_metrics_v39.csv",
                               "arm_bootstrap_v39.csv", "arm_placebo_v39.csv",
                               "arm_verdict_v39.csv")
    assert WR.RESULTS.name == "results" and WR.RESULTS.parent == COACH


def test_no_real_result_file_exists_yet():
    """This pass must not create them."""
    if WR.RESULTS.exists():
        assert not [p.name for p in WR.RESULTS.glob("*_v39.csv")]


# =====================================================================================================
# 2. THE OUTPUT CONTRACT — extra, missing, pre-existing, partial
# =====================================================================================================
def test_a_missing_frame_refuses(tmp_path):
    f = synth_frames(); f.pop("placebo")
    with pytest.raises(WR.ResultWriteError) as e:
        WR.write_results(f, out_dir=tmp_path)
    assert "placebo" in str(e.value)
    assert not list(tmp_path.glob("*.csv"))


def test_an_EXTRA_frame_refuses_rather_than_being_dropped(tmp_path):
    f = synth_frames(); f["surprise"] = pd.DataFrame({"a": [1]})
    with pytest.raises(WR.ResultWriteError) as e:
        WR.write_results(f, out_dir=tmp_path)
    assert "surprise" in str(e.value)


def test_an_empty_frame_refuses(tmp_path):
    f = synth_frames(); f["selection"] = pd.DataFrame()
    with pytest.raises(WR.ResultWriteError) as e:
        WR.write_results(f, out_dir=tmp_path)
    assert "empty" in str(e.value)
    assert not list(tmp_path.glob("*.csv"))


def test_a_PRE_EXISTING_output_refuses_without_the_overwrite_flag(tmp_path):
    WR.write_results(synth_frames(), out_dir=tmp_path)
    with pytest.raises(WR.ResultWriteError) as e:
        WR.write_results(synth_frames(), out_dir=tmp_path)
    assert "overwrite=True" in str(e.value)


def test_the_overwrite_flag_is_SEPARATELY_tested_and_works(tmp_path):
    first = WR.write_results(synth_frames(seed=1), out_dir=tmp_path)
    second = WR.write_results(synth_frames(seed=2), out_dir=tmp_path, overwrite=True)
    assert sorted(first) == sorted(second) == sorted(WR.RESULT_FILES)
    assert first["arm_metrics_v39.csv"] != second["arm_metrics_v39.csv"], (
        "overwrite did not actually replace the content")


def test_a_PARTIAL_write_fails_closed_and_leaves_nothing(tmp_path, monkeypatch):
    """The 3rd file explodes; the 1st and 2nd must be removed, not left behind."""
    calls = {"n": 0}
    real_to_csv = pd.DataFrame.to_csv

    def flaky(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disk full (injected)")
        return real_to_csv(self, *a, **k)

    monkeypatch.setattr(pd.DataFrame, "to_csv", flaky)
    with pytest.raises(OSError):
        WR.write_results(synth_frames(), out_dir=tmp_path)
    assert not list(tmp_path.glob("*.csv")), "a partial result set survived"
    assert not list(tmp_path.glob("*.partial")), "a temp file was left behind"


def test_hashes_are_emitted_only_after_all_five_land(tmp_path):
    hashes = WR.write_results(synth_frames(), out_dir=tmp_path)
    assert len(hashes) == 5
    for name, h in hashes.items():
        assert len(h) == 64
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == h


def test_the_writer_is_the_ONLY_module_that_writes_results():
    """Neither v3.9 module may write these; both are under their own write prohibitions."""
    for mod in ("run_coach_projection_experiment_v39.py", "assemble_real_panel_v39.py"):
        src = (COACH / mod).read_text(encoding="utf-8")
        for name in WR.RESULT_FILES:
            assert f'to_csv({name}' not in src
        assert ".to_parquet(" not in src or mod != "run_coach_projection_experiment_v39.py"


# =====================================================================================================
# 3. LOSSLESS FIVE-FILE MAPPING — round-trip from the serialized files
# =====================================================================================================
def test_every_returned_frame_reaches_a_file():
    assert set(WR.FRAME_TO_FILE) == set(WR.REQUIRED_FRAMES)
    assert set(WR.FRAME_TO_FILE.values()) == set(WR.RESULT_FILES)


def test_the_ORACLE_frame_is_recoverable_EXACTLY_from_the_serialized_metrics(tmp_path):
    frames = synth_frames()
    WR.write_results(frames, out_dir=tmp_path)
    on_disk = pd.read_csv(tmp_path / "arm_metrics_v39.csv")
    recovered = WR.recover_oracle(on_disk)
    expected = frames["oracle"].reset_index(drop=True)
    pd.testing.assert_frame_equal(recovered[list(expected.columns)], expected,
                                  check_dtype=False)


def test_the_METRICS_frame_is_recoverable_EXACTLY_from_the_serialized_metrics(tmp_path):
    frames = synth_frames()
    WR.write_results(frames, out_dir=tmp_path)
    on_disk = pd.read_csv(tmp_path / "arm_metrics_v39.csv")
    recovered = WR.recover_metrics(on_disk)
    expected = frames["metrics"].reset_index(drop=True)
    pd.testing.assert_frame_equal(recovered[list(expected.columns)], expected, check_dtype=False)


def test_the_PREFLIGHT_record_is_recoverable_EXACTLY_from_the_serialized_verdict(tmp_path):
    frames = synth_frames()
    WR.write_results(frames, out_dir=tmp_path)
    on_disk = pd.read_csv(tmp_path / "arm_verdict_v39.csv")
    recovered = WR.recover_preflight(on_disk)
    expected = frames["preflight"].reset_index(drop=True)
    pd.testing.assert_frame_equal(recovered[list(expected.columns)], expected, check_dtype=False)


def test_the_VERDICT_frame_is_recoverable_EXACTLY_from_the_serialized_verdict(tmp_path):
    frames = synth_frames()
    WR.write_results(frames, out_dir=tmp_path)
    on_disk = pd.read_csv(tmp_path / "arm_verdict_v39.csv")
    recovered = WR.recover_verdict(on_disk)
    expected = frames["verdict"].reset_index(drop=True)
    pd.testing.assert_frame_equal(recovered[list(expected.columns)], expected, check_dtype=False)


def test_the_discriminators_are_explicit_and_present(tmp_path):
    WR.write_results(synth_frames(), out_dir=tmp_path)
    metrics = pd.read_csv(tmp_path / "arm_metrics_v39.csv")
    assert WR.RECORD_TYPE in metrics.columns
    assert set(metrics[WR.RECORD_TYPE]) == {WR.METRIC_RECORD, WR.ORACLE_RECORD}
    verdict = pd.read_csv(tmp_path / "arm_verdict_v39.csv")
    assert any(c.startswith(WR.PREFLIGHT_PREFIX) for c in verdict.columns)


def test_no_oracle_or_preflight_FIELD_is_dropped(tmp_path):
    frames = synth_frames()
    WR.write_results(frames, out_dir=tmp_path)
    metrics = pd.read_csv(tmp_path / "arm_metrics_v39.csv")
    for c in frames["oracle"].columns:
        assert c in metrics.columns, f"oracle field {c} was dropped"
    verdict = pd.read_csv(tmp_path / "arm_verdict_v39.csv")
    for c in frames["preflight"].columns:
        assert c == "position" or WR.PREFLIGHT_PREFIX + c in verdict.columns, f"{c} dropped"


# =====================================================================================================
# 4. THE PANEL ADAPTER
# =====================================================================================================
def test_GREEN_the_adapter_produces_the_panel_run_experiment_needs():
    a = assembled()
    panel, report = ARP.panel_for_experiment(a, require_bucket_coverage=False)
    assert ARP.MODEL_TARGET_COLUMN in panel.columns
    assert ARP.OUTCOME_COLUMN not in panel.columns, "the outcome name survived into the panel"
    assert "bucket" in panel.columns and set(panel["bucket"]) == {"veteran"}
    assert len(panel) == len(a["features"]) == report["n_rows"]
    assert list(panel[list(ARP.PANEL_KEYS)].itertuples(index=False)) == \
        list(a["features"][list(ARP.PANEL_KEYS)].itertuples(index=False)), "row order changed"
    # `y` is the sanctioned target at this boundary and IS in FORBIDDEN_IN_FEATURES by design;
    # every OTHER outcome-bearing name must be absent, and the target must not reach a feature list.
    assert (set(panel.columns) & ARP.FORBIDDEN_IN_FEATURES) == {ARP.MODEL_TARGET_COLUMN}
    feats = ARP.panel_feature_columns(panel)
    assert ARP.MODEL_TARGET_COLUMN not in feats and "outcome_state" not in feats
    assert not (set(feats) & ARP.FORBIDDEN_IN_FEATURES)


def test_the_adapter_retains_and_reports_the_accounting_states():
    """Two feature rows have NO weekly-stat row, so production zero-fills them; the adapter must
    carry that state onto the panel rather than dropping it."""
    f = synth_features()
    o = synth_outcomes(f).iloc[2:].reset_index(drop=True)      # 2 rows with no stat row
    panel, report = ARP.panel_for_experiment(ARP.assemble_panel_core(f, o),
                                             require_bucket_coverage=False)
    assert "outcome_state" in panel.columns
    assert report["outcome_states"].get(ARP.STATE_ZERO_FILLED, 0) == 2
    assert report["accounting"][ARP.STATE_ZERO_FILLED] == 2
    assert (panel.loc[panel["outcome_state"] == ARP.STATE_ZERO_FILLED,
                      ARP.MODEL_TARGET_COLUMN] == 0.0).all()


def test_the_adapter_refuses_DUPLICATE_outcome_keys():
    f = synth_features()
    o = synth_outcomes(f)
    a = ARP.assemble_panel_core(f, o)
    a["outcomes"] = pd.concat([a["outcomes"], a["outcomes"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(a, require_bucket_coverage=False)
    assert "duplicate" in str(e.value).lower()


def test_the_adapter_refuses_a_MISSING_outcome_key():
    """Built AFTER assembly: `assemble_panel_core` zero-fills a missing stat row by design, so the
    gap the adapter must catch is an outcome frame that lost a row downstream of it."""
    f = synth_features()
    a = ARP.assemble_panel_core(f, synth_outcomes(f))
    a["outcomes"] = a["outcomes"].iloc[1:].reset_index(drop=True)
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(a, require_bucket_coverage=False)
    assert "no outcome key" in str(e.value)


def test_the_adapter_refuses_an_EXTRA_outcome_key():
    f = synth_features()
    a = ARP.assemble_panel_core(f, synth_outcomes(f))
    extra = a["outcomes"].iloc[[0]].copy()
    extra[ARP.PLAYER_KEY] = "00-9999999"
    a["outcomes"] = pd.concat([a["outcomes"], extra], ignore_index=True)
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(a, require_bucket_coverage=False)
    assert "match no feature row" in str(e.value)


def test_the_adapter_is_INSENSITIVE_to_outcome_row_order_but_preserves_feature_order():
    """A reordered outcome frame is fine — the join is on keys — but the PANEL order is the
    feature order, which is what the population contract depends on."""
    f = synth_features()
    a = ARP.assemble_panel_core(f, synth_outcomes(f))
    a["outcomes"] = a["outcomes"].iloc[::-1].reset_index(drop=True)
    panel, _ = ARP.panel_for_experiment(a, require_bucket_coverage=False)
    assert list(panel[ARP.PLAYER_KEY]) == list(f[ARP.PLAYER_KEY])
    assert list(panel[ARP.SEASON_KEY]) == list(f[ARP.SEASON_KEY])


def test_the_adapter_joins_ONLY_on_the_frozen_panel_keys():
    import inspect
    src = inspect.getsource(ARP.panel_for_experiment)
    assert "PANEL_KEYS" in src
    assert 'on=keys' in src


def test_the_target_is_renamed_ONLY_at_this_boundary():
    a = assembled()
    assert ARP.OUTCOME_COLUMN in a["outcomes"].columns, "upstream must still use the real name"
    panel, _ = ARP.panel_for_experiment(a, require_bucket_coverage=False)
    assert ARP.MODEL_TARGET_COLUMN in panel.columns
    assert ARP.OUTCOME_COLUMN not in panel.columns


def test_the_adapter_refuses_a_feature_frame_that_fails_its_validator():
    a = assembled()
    a["features"] = a["features"].drop(columns=["prior_ppg"])
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(a, require_bucket_coverage=False)
    assert "adapter input" in str(e.value)


def test_the_bucket_coverage_guard_REFUSES_an_incomplete_panel():
    """A veteran-only panel cannot feed the three rookie buckets. `run_experiment` would SKIP them
    silently, shrinking the population, so the adapter refuses instead."""
    a = assembled()
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(a, require_bucket_coverage=True)
    msg = str(e.value)
    assert "SILENTLY shrink the population" in msg
    for pos in ("RB", "WR", "TE"):
        assert f"{pos}/rookie" in msg


def test_panel_bucket_gaps_names_every_unfeedable_bucket():
    panel, _ = ARP.panel_for_experiment(assembled(), require_bucket_coverage=False)
    gaps = ARP.panel_bucket_gaps(panel)
    assert gaps, "a veteran-only panel must report gaps"
    assert all(any(f"{p}/rookie" in g for g in gaps) for p in ("RB", "WR", "TE"))


# =====================================================================================================
# 5. THE CLI — one authorized path, unreachable while locked
# =====================================================================================================
def test_the_dead_end_real_flag_is_GONE_and_there_is_ONE_authorized_path():
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    assert '"--real"' not in src, "the unconditional --real dead end must be removed"
    assert '"--run-mode"' in src and '"--outer-seasons"' in src
    assert src.count("def run_authorized_real") == 1


@pytest.mark.parametrize("spec,expected", [("2018-2025", tuple(range(2018, 2026))),
                                           ("2019,2020", (2019, 2020)),
                                           ("2024", (2024,))])
def test_outer_season_parsing(spec, expected):
    assert EX.parse_outer_seasons(spec) == expected


@pytest.mark.parametrize("bad", ["2013-2025", "2026", "1999", ""])
def test_outer_seasons_outside_the_frozen_set_refuse(bad):
    with pytest.raises(SystemExit):
        EX.parse_outer_seasons(bad)


@pytest.mark.parametrize("constant_open,env_open", [(False, False), (True, False), (False, True)])
def test_every_closed_or_PARTIAL_lock_state_reaches_ZERO_readers(monkeypatch, constant_open, env_open):
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", constant_open, raising=False)
    if env_open:
        monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    else:
        monkeypatch.delenv(EX.REAL_FIT_ENV_SWITCH, raising=False)

    reads = []
    monkeypatch.setattr(ARP, "authorized_feature_reader",
                        lambda *a, **k: reads.append("feature") or (lambda: None))
    monkeypatch.setattr(ARP, "authorized_outcome_reader",
                        lambda *a, **k: reads.append("outcome") or (lambda: None))
    with pytest.raises(RuntimeError):
        EX.run_authorized_real((2024,), 10, 2, verbose=False)
    assert reads == [], "a reader was constructed in a non-authorized lock state"


def test_the_synthetic_run_mode_never_reaches_the_real_path(monkeypatch):
    called = []
    monkeypatch.setattr(EX, "run_authorized_real", lambda *a, **k: called.append(1))
    monkeypatch.setattr(sys, "argv", ["prog", "--run-mode", "synthetic_prefit"])
    EX.main()
    assert called == [], "synthetic_prefit reached the authorized-real path"


def test_an_authorized_real_invocation_is_BLOCKED_while_the_locks_are_shut(monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["prog", "--run-mode", "authorized_real", "--outer-seasons", "2018-2025"])
    with pytest.raises(SystemExit) as e:
        EX.main()
    assert "BLOCKED" in str(e.value)


def test_the_authorized_path_order_is_authorization_then_clearance_then_readers():
    import inspect
    src = inspect.getsource(EX.run_authorized_real)
    # strip the docstring: it NARRATES the same order, so a raw index() matches prose, not code
    body = src.split('"""')
    src = body[0] + ("".join(body[2:]) if len(body) > 2 else "")
    i_auth = src.index("require_real_fit_authorization(authorization)")
    i_reset = src.index("reset_pipeline_assertions()")
    i_pre = src.index("PREFLIGHT_PHASE_PRE_RUN")
    i_clear = src.index("require_preflight_clearance(")
    i_read = src.index("authorized_composed_feature_reader")
    i_panel = src.index("assemble_real_panel(")
    i_adapt = src.index("panel_for_experiment")
    i_run = src.index("run_experiment(")
    i_post = src.index("PREFLIGHT_PHASE_POST_PIPELINE")
    i_postclear = src.index("require_post_pipeline_clearance(")
    i_compose = src.index("compose(")
    i_write = src.index("write_results(")
    # v3.9w: the counters are reset and the PRE_RUN preflight is taken before clearance, and the
    # POST_PIPELINE preflight and its clearance both precede compose and write.
    assert i_auth < i_reset < i_pre < i_clear < i_read < i_panel < i_adapt < i_run
    assert i_run < i_post < i_postclear < i_compose < i_write


# =====================================================================================================
# 6. SYNTHETIC END-TO-END through adapter + writer, into a temp directory
# =====================================================================================================
def test_SYNTHETIC_end_to_end_adapter_then_experiment_then_writer(tmp_path):
    """A full pass with SYNTHETIC targets: adapter -> run_experiment -> five files in a temp dir.

    No lock is opened, no real reader runs, and nothing is written outside `tmp_path`.
    """
    panel = EX.synthetic_panel(seasons=range(2014, 2021),
                               teams=["ARI", "ATL", "BAL", "BUF", "CAR", "CHI"],
                               players_per_team=2, positions=["RB"], seed=11)
    coach_a = pd.read_csv(EX.DATA / "team_coach_features_design_a_v39.csv")
    coach_b = pd.read_csv(EX.DATA / "team_coach_features_design_b_oracle_v39.csv")
    EX.reset_pipeline_assertions()
    frames = EX.run_experiment(panel, coach_a, coach_b, outer_seasons=[2020], positions=["RB"],
                               bootstrap_draws=25, run_placebo=True, placebo_draws=3, verbose=False)
    assert set(WR.REQUIRED_FRAMES) <= set(frames)

    hashes = WR.write_results(frames, out_dir=tmp_path)
    assert sorted(hashes) == sorted(WR.RESULT_FILES)
    for name in WR.RESULT_FILES:
        assert (tmp_path / name).exists() and len(pd.read_csv(tmp_path / name))

    # the merged files round-trip
    metrics = pd.read_csv(tmp_path / "arm_metrics_v39.csv")
    assert set(metrics[WR.RECORD_TYPE]) <= {WR.METRIC_RECORD, WR.ORACLE_RECORD}
    assert len(WR.recover_metrics(metrics)) == len(frames["metrics"])
    assert EX.real_fit_lock_state() == (False, False)


def test_the_end_to_end_wrote_nothing_outside_the_temp_dir(tmp_path):
    before = sorted(p.name for p in EX.DATA.glob("*_v39.*"))
    WR.write_results(synth_frames(), out_dir=tmp_path)
    after = sorted(p.name for p in EX.DATA.glob("*_v39.*"))
    assert before == after
    assert len(after) == 5


# =====================================================================================================
# 7. Nothing production moved
# =====================================================================================================
def test_production_models_and_pinned_inputs_are_unchanged():
    pf = EX.preflight(phase=EX.PREFLIGHT_PHASE_PRE_RUN)
    for check in ("protected_hashes", "production_models_identical", "v39_artifacts_pinned",
                  "no_unauthorized_v39_artifact", "no_coaching_parquet"):
        assert pf["checks"][check]["ok"] is True, pf["checks"][check]["detail"]
    assert ARP.verify_pinned_activation_inputs(strict=False) == []


def test_the_locks_are_still_shut_and_the_gate_still_refuses():
    pf = EX.preflight(pipeline_assertions={k: 3 for k in EX._PIPELINE_ASSERTIONS})
    assert pf["all_ok"] is True and pf["n_checks"] == 21
    assert EX.REAL_FIT_AUTHORIZED is False
    assert EX.real_fit_lock_state() == (False, False)
    assert ARP.authorized_real_gate(pf)[0] is False
