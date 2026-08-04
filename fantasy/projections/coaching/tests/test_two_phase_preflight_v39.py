"""v3.9w — the TWO-PHASE 21-check preflight, and the blind spot that hid the circular timing gate.

WHAT FAILED. The first authorized real run refused at pre-run clearance:

    gate 1 (authorized preflight): check(s) not explicitly ok: ['pipeline_timing_assertions_ran']

`preflight()` demanded that every `_PIPELINE_ASSERTIONS` counter be non-zero, but those counters are
incremented BY `run_experiment`, which runs AFTER clearance. The authorized path could not clear its
own gate. No outcome was read, no model was fit and no result file landed — the refusal was total.

WHY NO TEST CAUGHT IT. Every test that exercised the authorized path either passed
`pipeline_assertions={k: 3 ...}` or replaced `require_preflight_clearance` with a stub. Both supply a
value the real path cannot produce, so the real path's inability to produce it was never observable.

WHAT THIS MODULE DOES. It exercises the REAL `run_authorized_real` control flow with SYNTHETIC injected
readers, the REAL preflight functions, no injected counters and no stubbed clearance — the exact
configuration under which the defect would have been visible. Plus the phase semantics, the refusals in
both directions, and the frozen CLI draw counts.

NOTHING HERE READS A REAL FANTASY OUTCOME. The outcome reader is synthetic and deterministic; the
feature side uses the pinned repo-owned FEATURE snapshots, which carry no outcome column (that is what
contract C4 and `validate_feature_frame` enforce). Results are written to `tmp_path`, never to
`coaching/results/`.
"""
import hashlib
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

HERE = pathlib.Path(__file__).resolve().parent
COACH = HERE.parent
if str(COACH) not in sys.path:
    sys.path.insert(0, str(COACH))

import run_coach_projection_experiment_v39 as EX          # noqa: E402
import assemble_real_panel_v39 as ARP                     # noqa: E402
import write_v39_results as WR                            # noqa: E402


# =====================================================================================================
# helpers
# =====================================================================================================
def _capability():
    """The invocation-scoped capability. It opens no file lock and mutates no module state."""
    return EX.grant_real_fit_authorization(EX.REAL_FIT_CLI_TOKEN,
                                           env={EX.REAL_FIT_ENV_SWITCH: EX.REAL_FIT_ENV_TOKEN})


def _synthetic_outcome_reader(feature_frame):
    """A DETERMINISTIC fabricated target for exactly the supplied feature keys.

    Derived from a hash of the row key, so it is reproducible and carries no information from any real
    fantasy outcome. It satisfies `validate_outcome_frame`'s contract: the panel keys plus the target.
    """
    keys = feature_frame[list(ARP.PANEL_KEYS)].drop_duplicates().reset_index(drop=True)

    def _read():
        out = keys.copy()
        digest = [int(hashlib.sha256("|".join(str(v) for v in row).encode()).hexdigest()[:8], 16)
                  for row in keys.itertuples(index=False)]
        out[ARP.OUTCOME_COLUMN] = np.asarray(digest, dtype=float) % 300.0
        return out
    return _read


SAMPLE_PER_GROUP = 26          # > COHORT_N for every position, so every outer cohort is complete


@pytest.fixture(scope="module")
def small_feature_frame():
    """A SMALL feature frame with the real schema — the injected reader's payload.

    Sampled deterministically (`head`, no RNG) from the pinned FEATURE snapshots, stratified by
    (season, position, rookie/veteran) so the frozen 87-column contract, every panel season and all
    seven shipped Arm 0 buckets survive the reduction. The point of this test is the CONTROL FLOW and
    the gate ORDER, not the estimates, so the panel is cut to what runs in seconds. Features carry no
    outcome column — that is what `validate_feature_frame` enforces on the way in.
    """
    full = ARP.authorized_composed_feature_reader()()
    eligible, _ = ARP.evaluation_eligibility(full)
    small = (eligible.sort_values(list(ARP.PANEL_KEYS))
             .groupby(["season", "position", "is_rookie"], sort=False, group_keys=False)
             .head(SAMPLE_PER_GROUP)
             .reset_index(drop=True))
    assert set(small["season"]) == set(eligible["season"]), "a panel season was dropped"
    return small


@pytest.fixture
def synthetic_sources(small_feature_frame):
    return (lambda: small_feature_frame.copy()), _synthetic_outcome_reader(small_feature_frame)


def _run(tmp_path, sources, **kw):
    """The REAL `run_authorized_real`, with only the readers and the output directory redirected."""
    features, outcomes = sources
    return EX.run_authorized_real(
        kw.pop("outer_seasons", (2025,)), kw.pop("bootstrap_draws", 40),
        kw.pop("placebo_draws", 1), out_dir=tmp_path, verbose=False,
        authorization=kw.pop("authorization", None) or _capability(),
        feature_source=features, outcome_source=outcomes,
        positions=kw.pop("positions", ("TE",)), **kw)


def _result_files(d):
    return sorted(p.name for p in pathlib.Path(d).glob("*") if p.is_file())


def _fast_pipeline(monkeypatch, assertions="all"):
    """Replace ONLY `run_experiment` with a fast stand-in that increments the REAL counters.

    The gates under test — both `preflight` phases, `require_preflight_clearance` and
    `require_post_pipeline_clearance` — are the REAL functions in every test that uses this. The
    nested pipeline itself costs ~140 model fits per position-season and is exercised end to end once,
    by `test_the_REAL_authorized_control_flow_...`; re-running it in each failure-mode test would buy
    no additional coverage of the gate ordering.

    `assertions` selects which counters the stand-in records: "all", "none", or a name to omit.
    """
    def fake(panel, coach_a, coach_b=None, **kw):
        for name in EX.FROZEN_PIPELINE_ASSERTION_NAMES:
            if assertions == "none" or name == assertions:
                continue
            EX._note_assertion(name)
        idx = pd.DataFrame({"position": ["TE"], "value": [1.0]})
        return {k: idx.copy() for k in WR.REQUIRED_FRAMES}

    monkeypatch.setattr(EX, "run_experiment", fake)


# =====================================================================================================
# 1. the phase vocabulary
# =====================================================================================================
def test_the_phase_vocabulary_is_frozen_and_shared_by_value():
    assert EX.PREFLIGHT_PHASES == ("pre_run", "post_pipeline")
    assert ARP.PREFLIGHT_PHASES == EX.PREFLIGHT_PHASES
    assert EX.PREFLIGHT_PHASE_PRE_RUN == ARP.PREFLIGHT_PHASE_PRE_RUN == "pre_run"
    assert EX.PREFLIGHT_PHASE_POST_PIPELINE == ARP.PREFLIGHT_PHASE_POST_PIPELINE == "post_pipeline"


def test_frozen_pipeline_assertion_names():
    """Pinned BY VALUE: deleting a counter must not silently narrow the post-pipeline requirement."""
    assert EX.FROZEN_PIPELINE_ASSERTION_NAMES == (
        "inner_fold_timing", "outer_no_self_train",
        "identical_rows_across_arms", "coach_join_preserved_rows")
    assert set(EX.FROZEN_PIPELINE_ASSERTION_NAMES) == set(EX._PIPELINE_ASSERTIONS)


@pytest.mark.parametrize("bad", [None, "", "PRE_RUN", "prerun", "post", True, 0, 1, (), ["pre_run"]])
def test_missing_unknown_or_malformed_phases_are_REFUSED(bad):
    with pytest.raises(ValueError):
        EX.validate_preflight_phase(bad)
    with pytest.raises(ValueError):
        EX.preflight(phase=bad)


def test_the_check_is_named_truthfully_in_both_phases():
    """`..._ran` was FALSE in pre_run, where the check passes because they have NOT run."""
    assert "pipeline_timing_assertion_state" in EX.PREFLIGHT_CHECKS
    assert "pipeline_timing_assertions_ran" not in EX.PREFLIGHT_CHECKS
    assert len(EX.PREFLIGHT_CHECKS) == 21
    assert tuple(ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS) == tuple(EX.PREFLIGHT_CHECKS)


# =====================================================================================================
# 2. phase-aware semantics — neither phase is disabled or faked
# =====================================================================================================
def test_pre_run_requires_every_counter_to_be_exactly_zero():
    EX.reset_pipeline_assertions()
    pf = EX.preflight(phase=EX.PREFLIGHT_PHASE_PRE_RUN)
    c = pf["checks"]["pipeline_timing_assertion_state"]
    assert c["ok"] is True and "has not yet executed" in c["detail"]


def test_a_STALE_nonzero_counter_FAILS_pre_run():
    EX.reset_pipeline_assertions()
    EX._note_assertion("inner_fold_timing")
    c = EX.preflight(phase=EX.PREFLIGHT_PHASE_PRE_RUN)["checks"]["pipeline_timing_assertion_state"]
    assert c["ok"] is False
    assert "stale" in c["detail"] and "inner_fold_timing" in c["detail"]


def test_post_pipeline_requires_every_counter_POSITIVE_and_NAMES_the_ones_that_did_not_run():
    zero = {k: 0 for k in EX.FROZEN_PIPELINE_ASSERTION_NAMES}
    c = EX.preflight(pipeline_assertions=zero,
                     phase=EX.PREFLIGHT_PHASE_POST_PIPELINE)["checks"]["pipeline_timing_assertion_state"]
    assert c["ok"] is False
    for name in EX.FROZEN_PIPELINE_ASSERTION_NAMES:
        assert name in c["detail"]


def test_ONE_missing_counter_fails_post_pipeline_and_is_named():
    partial = {k: 3 for k in EX.FROZEN_PIPELINE_ASSERTION_NAMES if k != "outer_no_self_train"}
    c = EX.preflight(pipeline_assertions=partial,
                     phase=EX.PREFLIGHT_PHASE_POST_PIPELINE)["checks"]["pipeline_timing_assertion_state"]
    assert c["ok"] is False and "outer_no_self_train" in c["detail"]


def test_a_boolean_counter_does_not_satisfy_post_pipeline():
    """`True > 0` in Python; a bool is not evidence that an assertion executed."""
    lying = {k: True for k in EX.FROZEN_PIPELINE_ASSERTION_NAMES}
    c = EX.preflight(pipeline_assertions=lying,
                     phase=EX.PREFLIGHT_PHASE_POST_PIPELINE)["checks"]["pipeline_timing_assertion_state"]
    assert c["ok"] is False


def test_the_result_carries_its_phase():
    for ph in EX.PREFLIGHT_PHASES:
        assert EX.preflight(phase=ph)["phase"] == ph


def test_BOTH_phases_evaluate_all_21_checks():
    for ph in EX.PREFLIGHT_PHASES:
        assert EX.preflight(phase=ph)["n_checks"] == 21


# =====================================================================================================
# 3. a phase result cannot be replayed as the other gate
# =====================================================================================================
def _shaped(phase):
    return {"all_ok": True, "run_mode": ARP.AUTHORIZED_RUN_MODE, "phase": phase,
            "n_checks": len(ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS), "n_failed": 0, "failures": {},
            "checks": {n: {"ok": True, "detail": "fixture"}
                       for n in ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS}}


def test_gate1_accepts_only_pre_run():
    assert ARP.validate_authorized_preflight(_shaped(EX.PREFLIGHT_PHASE_PRE_RUN)) == []
    problems = ARP.validate_authorized_preflight(_shaped(EX.PREFLIGHT_PHASE_POST_PIPELINE))
    assert any("phase" in p for p in problems)


def test_gate2_accepts_only_post_pipeline():
    assert ARP.validate_post_pipeline_preflight(_shaped(EX.PREFLIGHT_PHASE_POST_PIPELINE)) == []
    problems = ARP.validate_post_pipeline_preflight(_shaped(EX.PREFLIGHT_PHASE_PRE_RUN))
    assert any("phase" in p for p in problems)


@pytest.mark.parametrize("phase", [None, "bogus", 7, True])
def test_a_result_with_a_missing_or_unknown_phase_authorizes_NOTHING(phase):
    shaped = _shaped(EX.PREFLIGHT_PHASE_PRE_RUN)
    if phase is None:
        shaped.pop("phase")
    else:
        shaped["phase"] = phase
    assert ARP.validate_authorized_preflight(shaped)
    assert ARP.validate_post_pipeline_preflight(shaped)


def test_post_pipeline_clearance_REFUSES_a_pre_run_result_and_writes_nothing(tmp_path):
    with pytest.raises(RuntimeError) as e:
        EX.require_post_pipeline_clearance(_shaped(EX.PREFLIGHT_PHASE_PRE_RUN),
                                           authorization=_capability())
    assert "no result file may be written" in str(e.value)
    assert _result_files(tmp_path) == []


# =====================================================================================================
# 4. THE BLIND-SPOT TEST — the real control flow, no injected counters, no stubbed gate
# =====================================================================================================
@pytest.fixture(scope="module")
def end_to_end(tmp_path_factory):
    """ONE real end-to-end pass, shared by the tests below.

    The real `run_authorized_real` calls the real `preflight` twice and the real
    `require_preflight_clearance` / `require_post_pipeline_clearance`. Nothing supplies
    `pipeline_assertions`; NOTHING replaces a gate. Only the readers and the output directory are
    redirected. Module-scoped because the nested pipeline costs ~140 model fits.
    """
    import _pytest.monkeypatch
    tmp_path = tmp_path_factory.mktemp("end_to_end")
    monkeypatch = _pytest.monkeypatch.MonkeyPatch()
    full = ARP.authorized_composed_feature_reader()()
    eligible, _ = ARP.evaluation_eligibility(full)
    small = (eligible.sort_values(list(ARP.PANEL_KEYS))
             .groupby(["season", "position", "is_rookie"], sort=False, group_keys=False)
             .head(SAMPLE_PER_GROUP).reset_index(drop=True))
    sources = (lambda: small.copy()), _synthetic_outcome_reader(small)
    try:
        yield _observed_run(tmp_path, sources, monkeypatch)
    finally:
        monkeypatch.undo()


def _observed_run(tmp_path, synthetic_sources, monkeypatch):
    order = []
    real_pf, real_pre, real_post = EX.preflight, EX.require_preflight_clearance, \
        EX.require_post_pipeline_clearance
    real_write = WR.write_results

    def spy_pf(*a, **k):
        r = real_pf(*a, **k)
        order.append(("preflight", r["phase"], r["n_checks"] - r["n_failed"],
                      dict(EX._PIPELINE_ASSERTIONS)))
        return r

    def spy_pre(*a, **k):
        order.append(("clearance_pre_run", None, None, None))
        return real_pre(*a, **k)

    def spy_post(*a, **k):
        order.append(("clearance_post_pipeline", None, None, None))
        return real_post(*a, **k)

    def spy_write(*a, **k):
        order.append(("write", None, None, dict(EX._PIPELINE_ASSERTIONS)))
        return real_write(*a, **k)

    monkeypatch.setattr(EX, "preflight", spy_pf)
    monkeypatch.setattr(EX, "require_preflight_clearance", spy_pre)
    monkeypatch.setattr(EX, "require_post_pipeline_clearance", spy_post)
    monkeypatch.setattr(WR, "write_results", spy_write)

    EX._note_assertion("inner_fold_timing")          # stale state the runner must clear itself
    frames, hashes = _run(tmp_path, synthetic_sources)
    return dict(order=order, frames=frames, hashes=hashes, files=_result_files(tmp_path))


def test_the_REAL_authorized_control_flow_clears_BOTH_phases_and_only_then_writes(end_to_end):
    """This is the test whose absence let the circular gate reach the first real run.

    No `pipeline_assertions` is supplied anywhere and no gate is stubbed: the counters are OBSERVED at
    zero before the pipeline and positive after it, and both phases are 21/21 from the real preflight.
    """
    order = end_to_end["order"]
    stages = [o[0] for o in order]
    assert stages.index("clearance_pre_run") < stages.index("clearance_post_pipeline") < \
        stages.index("write"), stages

    pre = next(o for o in order if o[0] == "preflight" and o[1] == "pre_run")
    post = next(o for o in order if o[0] == "preflight" and o[1] == "post_pipeline")

    # the counters really did start at zero (the runner reset the stale one this test planted) and
    # really were incremented by the pipeline — no value was injected anywhere
    assert set(pre[3].values()) == {0}, pre[3]
    assert all(v > 0 for v in post[3].values()), post[3]

    # 21/21 in BOTH phases, derived from the real preflight
    assert pre[2] == 21 and post[2] == 21

    assert len(end_to_end["hashes"]) == 5
    assert set(end_to_end["files"]) == set(WR.RESULT_FILES)
    assert set(end_to_end["frames"]) >= set(WR.REQUIRED_FRAMES)


def test_the_pre_run_preflight_precedes_every_reader_in_the_real_flow(end_to_end):
    """The pre-run 21/21 is taken before the composed reader is even constructed."""
    order = end_to_end["order"]
    phases = [o[1] for o in order if o[0] == "preflight"]
    assert phases[0] == "pre_run", phases
    assert "post_pipeline" in phases


def test_the_per_position_C10_records_use_post_pipeline_semantics(end_to_end):
    """`run_experiment`'s own C10 rows still REQUIRE the assertions to have executed.

    They also prove the capability reaches them: `run_mode_locks` re-derives the lock state inside
    `run_experiment`, and before v3.9w the authorization was not forwarded, so every C10 record of a
    real run would have reported a lock failure it did not have.
    """
    pf_rows = end_to_end["frames"]["preflight"]
    assert len(pf_rows) and pf_rows["chk_pipeline_timing_assertion_state"].all()
    assert pf_rows["chk_run_mode_locks"].all()
    assert (pf_rows["n_checks"] == 21).all() and (pf_rows["n_failed"] == 0).all()
    assert (pf_rows["all_ok"]).all()


# =====================================================================================================
# 5. every failure mode leaves ZERO result files
# =====================================================================================================
def test_a_stale_counter_fails_pre_run_BEFORE_any_reader_and_writes_nothing(tmp_path):
    """The door itself, not the runner: `assemble_real_panel` does not reset, so staleness refuses."""
    calls = []

    def tripwire(name):
        def _r():
            calls.append(name)
            raise AssertionError(f"the {name} reader must never be called")
        return _r

    EX.reset_pipeline_assertions()
    EX._note_assertion("coach_join_preserved_rows")
    with pytest.raises((RuntimeError, ARP.AssemblyError)) as e:
        EX.assemble_real_panel(tripwire("feature"), tripwire("outcome"), _capability())
    assert "stale" in str(e.value) or "pipeline_timing_assertion_state" in str(e.value)
    assert calls == []
    assert _result_files(tmp_path) == []


def test_zero_counters_fail_post_pipeline_BEFORE_any_write(tmp_path, synthetic_sources, monkeypatch):
    """A pipeline that silently ran no assertion must not be able to publish a result."""
    _fast_pipeline(monkeypatch, assertions="none")
    wrote = []
    monkeypatch.setattr(WR, "write_results", lambda *a, **k: wrote.append(1))

    with pytest.raises(RuntimeError) as e:
        _run(tmp_path, synthetic_sources)
    assert "POST-PIPELINE CLEARANCE REFUSED" in str(e.value)
    assert wrote == [] and _result_files(tmp_path) == []


def test_one_missing_counter_fails_post_pipeline_before_any_write(tmp_path, synthetic_sources,
                                                                  monkeypatch):
    _fast_pipeline(monkeypatch, assertions="outer_no_self_train")
    wrote = []
    monkeypatch.setattr(WR, "write_results", lambda *a, **k: wrote.append(1))

    with pytest.raises(RuntimeError) as e:
        _run(tmp_path, synthetic_sources)
    assert "outer_no_self_train" in str(e.value)
    assert wrote == [] and _result_files(tmp_path) == []


def test_a_wrong_phase_result_refuses_the_run_and_writes_nothing(tmp_path, synthetic_sources,
                                                                 monkeypatch):
    """Feed the post-pipeline gate a pre-run-phase result: it must refuse before compose/write."""
    _fast_pipeline(monkeypatch)
    real_pf = EX.preflight

    def mislabelled(*a, **k):
        r = real_pf(*a, **k)
        if r["phase"] == EX.PREFLIGHT_PHASE_POST_PIPELINE:
            r = dict(r, phase=EX.PREFLIGHT_PHASE_PRE_RUN)
        return r

    monkeypatch.setattr(EX, "preflight", mislabelled)
    wrote = []
    monkeypatch.setattr(WR, "write_results", lambda *a, **k: wrote.append(1))

    with pytest.raises(RuntimeError) as e:
        _run(tmp_path, synthetic_sources)
    assert "phase" in str(e.value)
    assert wrote == [] and _result_files(tmp_path) == []


def test_no_capability_refuses_before_anything(tmp_path, synthetic_sources):
    features, outcomes = synthetic_sources
    with pytest.raises(RuntimeError):
        EX.run_authorized_real((2024,), 60, 3, out_dir=tmp_path, verbose=False,
                               authorization=None, feature_source=features,
                               outcome_source=outcomes, positions=("TE",))
    assert _result_files(tmp_path) == []


# =====================================================================================================
# 6. the frozen draw counts (the second half of the operational defect)
# =====================================================================================================
def test_the_frozen_draw_constants():
    assert EX.BOOTSTRAP_DRAWS == 20_000 and EX.PLACEBO_DRAWS == 200
    assert EX.SMOKE_BOOTSTRAP_DRAWS == 2000 and EX.SMOKE_PLACEBO_DRAWS == 10


def test_authorized_real_accepts_ONLY_the_frozen_draw_counts():
    assert EX.validate_authorized_draw_counts(20_000, 200)[0] is True
    for b, p in [(2000, 10), (2000, 200), (20_000, 10), (19_999, 200), (20_000, 201),
                 (20_000.0, 200), (True, 200), (None, 200), ("20000", 200)]:
        ok, detail = EX.validate_authorized_draw_counts(b, p)
        assert ok is False, (b, p)
        assert "frozen" in detail


def test_the_CLI_defaults_to_the_frozen_counts_in_authorized_real_and_refuses_others(monkeypatch,
                                                                                     capsys):
    """The documented command omitted the draw flags; the defaults were TEST-scale 2,000/10."""
    seen = {}

    def fake_run(seasons, bootstrap, placebo, **k):
        seen.update(bootstrap=bootstrap, placebo=placebo)
        return {}, {}

    monkeypatch.setattr(EX, "run_authorized_real", fake_run)
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    argv = ["x", "--run-mode", "authorized_real", "--authorization-token", EX.REAL_FIT_CLI_TOKEN,
            "--outer-seasons", "2024"]

    monkeypatch.setattr(sys, "argv", argv)
    EX.main()
    assert seen == {"bootstrap": 20_000, "placebo": 200}

    monkeypatch.setattr(sys, "argv", argv + ["--bootstrap-draws", "2000"])
    with pytest.raises(SystemExit) as e:
        EX.main()
    assert "frozen" in str(e.value)

    monkeypatch.setattr(sys, "argv", argv + ["--placebo-draws", "10"])
    with pytest.raises(SystemExit) as e:
        EX.main()
    assert "frozen" in str(e.value)


def test_the_documented_powershell_command_is_pinned_and_carries_the_frozen_draws():
    """CMD's `set NAME=value` does not set an environment variable in PowerShell — it was inert."""
    manifest = (COACH / "V39_ACTIVATION_MANIFEST.md").read_text(encoding="utf-8")
    assert ("$env:COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH="
            "'I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT'") in manifest
    assert "--bootstrap-draws 20000" in manifest and "--placebo-draws 200" in manifest
    assert "\nset COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH=" not in manifest


# =====================================================================================================
# 7. the repair changes no statistical rule
# =====================================================================================================
def test_no_frozen_statistical_constant_moved():
    assert EX.BOOTSTRAP_SEED == 20260728 and EX.PLACEBO_SEED == 20260728
    assert EX.MIN_RELATIVE_IMPROVEMENT == 0.01 and EX.TIE_BAND == 0.25
    assert EX.FULL_PANEL_TOLERANCE == 0.25
    assert EX.COHORT_N == {"QB": 12, "RB": 24, "WR": 24, "TE": 12}
    assert EX.REQUIRED_OUTER_SEASONS == tuple(range(2018, 2026))
    assert EX.REQUIRED_RECENT_SEASONS == tuple(range(2021, 2026))
    assert EX.INNER_MIN_TRAIN_SEASONS == 2 and EX.INNER_MIN_VALIDATION_SEASONS == 2


def test_the_source_lock_constant_is_still_closed():
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    assert "\nREAL_FIT_AUTHORIZED = False\n" in src
    assert EX.REAL_FIT_AUTHORIZED is False
