"""THE ACTIVATION WIRING — the implemented door, and every transition into it.

The entry point is no longer a `raise`. It is implemented under contract **C5-A**, and the seal has
MOVED rather than weakened:

  * statement 1 `require_real_fit_authorization()` refuses unless BOTH locks are open;
  * statement 2 `require_preflight_clearance()` refuses unless the run mode is `authorized_real`, both
    locks are open, preflight is 21/21 in `authorized_real` mode, `activation_readiness()` is True,
    `authorized_real_gate()` is True, and every pinned input matches its hash and manifest;
  * C5-A clause 3 forbids any reader callee in the body, so the module physically cannot read a file
    by itself — the readers are parameters, called only in statement 3, after clearance returns.

The decisive property, asserted below with tripwire readers: **with the locks closed, neither injected
reader is ever called.** That is the complete prohibition on real readers in `synthetic_prefit`.

NOTHING HERE READS A REAL OUTCOME. Every reader is a tripwire or a synthetic/temp-file reader written
by the test itself; the canonical weekly snapshot is never opened, and no model is fit.
"""
import ast
import contextlib
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


class ReaderTripwire:
    """Records every call. If the door ever reaches a reader unauthorized, `calls` is non-empty."""

    def __init__(self, name, payload=None):
        self.name, self.payload, self.calls = name, payload, []

    def __call__(self):
        self.calls.append(self.name)
        if self.payload is None:
            raise AssertionError(f"the {self.name} reader RAN while the door should have refused")
        return self.payload


def _capability():
    """Mint the invocation-scoped capability from the two exact tokens.

    SUPERSEDED ROUTE: this used to monkeypatch `REAL_FIT_AUTHORIZED = True`. That no longer authorizes
    anything — the constant is the default-closed invariant and is never consulted as an opener
    (v3.9v). Holding a capability opens nothing by itself; every reader below is still injected.
    """
    return EX.grant_real_fit_authorization(EX.REAL_FIT_CLI_TOKEN,
                                           env={EX.REAL_FIT_ENV_SWITCH: EX.REAL_FIT_ENV_TOKEN})


@contextlib.contextmanager
def _locks_open(monkeypatch_obj):
    """Kept for call-shape compatibility; yields the capability."""
    yield _capability()


# =====================================================================================================
# The source-level contract
# =====================================================================================================
def _door():
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    return next(n for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.FunctionDef) and n.name == "assemble_real_panel")


def test_the_declared_contract_mode_is_authorized_real_and_is_not_a_lock():
    """Which C5 variant applies is DECLARED, never inferred from the lock state."""
    assert EX.ENTRY_POINT_CONTRACT_MODE == EX.RUN_MODE_AUTHORIZED_REAL
    assert EX.DEFAULT_RUN_MODE == EX.RUN_MODE_SYNTHETIC_PREFIT, (
        "the contract mode must not drag the default RUN mode with it")
    assert EX.REAL_FIT_AUTHORIZED is False
    assert EX.real_fit_lock_state() == (False, False)


def test_the_door_satisfies_C5_A():
    ok = EX._entry_point_is_sealed(EX._executable_tree(
        (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")),
        contract_mode=EX.RUN_MODE_AUTHORIZED_REAL)
    assert ok == [], ok


def test_the_live_door_would_FAIL_C5_S_and_that_is_the_point():
    """RED: the two contracts are genuinely different, so the mode selection is load-bearing."""
    problems = EX._entry_point_is_sealed(EX._executable_tree(
        (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")),
        contract_mode=EX.RUN_MODE_SYNTHETIC_PREFIT)
    assert problems, "C5-S must reject an implemented door; otherwise the modes are interchangeable"
    assert any("C5-S" in p for p in problems)


def test_C5_S_still_ACCEPTS_the_sealed_shape():
    """The retired contract stays real and self-tested even though it is not the live one."""
    import boundary_corpus as BC
    src = BC._replace_entry_point(
        (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8"), BC.C5S_DOOR)
    assert EX._entry_point_is_sealed(EX._executable_tree(src),
                                     contract_mode=EX.RUN_MODE_SYNTHETIC_PREFIT) == []
    assert EX._entry_point_is_sealed(EX._executable_tree(src),
                                     contract_mode=EX.RUN_MODE_AUTHORIZED_REAL), (
        "C5-A must reject the sealed shape")


def test_an_unknown_contract_mode_is_refused():
    problems = EX._entry_point_is_sealed(EX._executable_tree("def assemble_real_panel(): pass"),
                                         contract_mode="whatever")
    assert problems and "unknown entry-point contract mode" in problems[0]


def test_the_door_body_is_exactly_three_statements_in_the_pinned_order():
    body = _door().body
    body = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    assert len(body) == 3
    assert body[0].value.func.id == "require_real_fit_authorization"
    assert body[1].value.func.id == EX.PREFLIGHT_CLEARANCE_NAME
    assert isinstance(body[2], ast.Return) and body[2].value.func.id == EX.PANEL_CORE_NAME


def test_the_door_contains_NO_reader_callee_at_all():
    """C5-A clause 3 — the module cannot read a file by itself; readers are parameters."""
    callees = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
               for n in ast.walk(_door()) if isinstance(n, ast.Call)}
    assert not (callees & EX.ENTRY_POINT_BANNED_READER_CALLEES), callees
    assert not (callees & EX.BANNED_OUTCOME_CALLEES), callees
    assert {"feature_reader", "outcome_reader"} <= callees, (
        "the readers must be INJECTED parameters that the door calls")


def test_the_readers_are_parameters_not_module_globals():
    args = [a.arg for a in _door().args.args]
    assert args[:2] == ["feature_reader", "outcome_reader"]


# =====================================================================================================
# THE DECISIVE TRANSITION — locks closed, no reader runs
# =====================================================================================================
def test_with_the_locks_CLOSED_the_door_refuses_and_no_reader_is_called():
    f, o = ReaderTripwire("feature"), ReaderTripwire("outcome")
    with pytest.raises(RuntimeError) as e:
        EX.assemble_real_panel(f, o)
    assert "NOT AUTHORIZED" in str(e.value).upper()
    assert f.calls == [] and o.calls == [], "a reader ran before authorization"


@pytest.mark.parametrize("constant_open,env_open", [(True, False), (False, True), (False, False)])
def test_every_PARTIAL_lock_state_refuses_before_any_reader(monkeypatch, constant_open, env_open):
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", constant_open, raising=False)
    if env_open:
        monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    else:
        monkeypatch.delenv(EX.REAL_FIT_ENV_SWITCH, raising=False)
    f, o = ReaderTripwire("feature"), ReaderTripwire("outcome")
    with pytest.raises(RuntimeError):
        EX.assemble_real_panel(f, o)
    assert f.calls == [] and o.calls == []


def test_a_synthetic_prefit_run_mode_refuses_even_with_BOTH_locks_open(monkeypatch):
    """The run mode is a separate gate from the capability, and it is checked before any reader."""
    auth = _capability()
    f, o = ReaderTripwire("feature"), ReaderTripwire("outcome")
    with pytest.raises(RuntimeError) as e:
        EX.assemble_real_panel(f, o, auth, run_mode=EX.RUN_MODE_SYNTHETIC_PREFIT)
    assert "run mode" in str(e.value)
    assert f.calls == [] and o.calls == []


def test_clearance_refuses_when_readiness_is_blocked(monkeypatch):
    auth = _capability()
    monkeypatch.setattr(ARP, "ROOKIE_MATRIX", COACH / "no_such_matrix.parquet")
    f, o = ReaderTripwire("feature"), ReaderTripwire("outcome")
    with pytest.raises(RuntimeError) as e:
        EX.assemble_real_panel(f, o, auth)
    assert "readiness" in str(e.value) or "rookie matrix missing" in str(e.value)
    assert f.calls == [] and o.calls == []


def _authorized_shaped_preflight():
    """A preflight result SHAPED as an authorized-real pass. Constructed, never a real clearance.

    Injecting a cleared result is what lets the LATER gates be tested at all — and it is also how a
    real authorized run works: the run passes the preflight it already cleared, rather than
    re-deriving a different one inside the door. It is shaped as a PRE_RUN result, the only phase
    `require_preflight_clearance` accepts (v3.9w).
    """
    return {"all_ok": True, "run_mode": ARP.AUTHORIZED_RUN_MODE,
            "phase": ARP.PREFLIGHT_PHASE_PRE_RUN,
            "n_checks": len(ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS), "n_failed": 0, "failures": {},
            "checks": {n: {"ok": True, "detail": "synthetic fixture"}
                       for n in ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS}}


def test_clearance_reaches_and_ENFORCES_the_input_pins(monkeypatch):
    """With every earlier gate injected clear, a drifted input pin is what refuses."""
    auth = _capability()
    EX.require_preflight_clearance(preflight_result=_authorized_shaped_preflight(),
                                   authorization=auth)
    monkeypatch.setattr(ARP, "WEEKLY_SNAPSHOT_SHA256", "0" * 64)
    with pytest.raises(ARP.AssemblyError) as e:
        EX.require_preflight_clearance(preflight_result=_authorized_shaped_preflight(),
                                       authorization=auth)
    assert "sha256" in str(e.value)


def test_a_drifted_input_stops_the_door_before_any_reader(monkeypatch):
    auth = _capability()
    monkeypatch.setattr(ARP, "WEEKLY_SNAPSHOT_SHA256", "0" * 64)
    f, o = ReaderTripwire("feature"), ReaderTripwire("outcome")
    with pytest.raises((RuntimeError, ARP.AssemblyError)):
        EX.assemble_real_panel(f, o, auth)
    assert f.calls == [] and o.calls == []


def test_clearance_refuses_a_gate_that_is_not_authorized_shaped(monkeypatch):
    with pytest.raises(RuntimeError) as e:
        EX.require_preflight_clearance(preflight_result={"all_ok": True},
                                       authorization=_capability())
    assert "REFUSED" in str(e.value)


def test_clearance_ORDER_gates_before_inputs(monkeypatch):
    """A blocked gate must refuse before the input pins are even consulted."""
    seen = {"inputs": 0}

    def spy():
        seen["inputs"] += 1
        raise AssertionError("input verification ran despite a blocked gate")

    monkeypatch.setattr(ARP, "verify_pinned_activation_inputs", spy)
    with pytest.raises(RuntimeError):
        EX.require_preflight_clearance(run_mode=EX.RUN_MODE_SYNTHETIC_PREFIT)
    assert seen["inputs"] == 0


# =====================================================================================================
# GREEN — the door DOES open, against synthetic/temp fixtures only
# =====================================================================================================
def _synthetic_features(seasons=ARP.ALL_PANEL_SEASONS, players=4, seed=5):
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for i in range(players):
            r = {c: float(rng.normal()) for c in ARP.ARM0_VETERAN_FEATURES}
            r.update({ARP.PLAYER_KEY: f"00-{i:07d}", "player": f"P{i}", "norm_name": f"p{i}",
                      "position": "RB", "team": "ARI", ARP.SEASON_KEY: int(s),
                      "reconstructed": 0, "is_rookie": 0})
            rows.append(r)
    # v3.9x: emit the CANONICAL panel-key dtypes, exactly as both real readers now do.
    return ARP.canonicalize_panel_keys(
        pd.DataFrame(rows)[list(ARP.VETERAN_FEATURE_COLUMNS)], "_synthetic_features")


def _synthetic_outcomes(features, seed=6):
    """A SYNTHETIC target. Not a fantasy outcome — generated here, from nothing."""
    rng = np.random.default_rng(seed)
    out = features[list(ARP.PANEL_KEYS)].copy()
    out[ARP.OUTCOME_COLUMN] = rng.normal(150, 40, size=len(out)).round(2)
    # v3.9x: emit the CANONICAL panel-key dtypes, exactly as both real readers now do.
    return ARP.canonicalize_panel_keys(out, "_synthetic_outcomes")


def test_GREEN_the_door_opens_and_assembles_when_every_gate_clears(monkeypatch):
    """Proves the wiring is not hard-wired shut. Synthetic frames; no canonical file is read."""
    feats = _synthetic_features()
    outs = _synthetic_outcomes(feats)
    auth = _capability()
    monkeypatch.setattr(EX, "require_preflight_clearance",
                        lambda *a, **k: {"all_ok": True, "injected": True})
    f = ReaderTripwire("feature", payload=feats)
    o = ReaderTripwire("outcome", payload=outs)
    result = EX.assemble_real_panel(f, o, auth)
    assert f.calls == ["feature"] and o.calls == ["outcome"]
    assert set(result) == {"features", "outcomes", "accounting", "seasons"}
    assert len(result["outcomes"]) == len(feats)
    assert ARP.OUTCOME_COLUMN not in result["features"].columns


def test_GREEN_production_zero_fill_and_accounting_survive_the_door(monkeypatch):
    """The door must not change `assemble_panel_core`'s production semantics."""
    feats = _synthetic_features()
    outs = _synthetic_outcomes(feats).iloc[:-3]          # 3 rows with no stat row -> zero-filled
    auth = _capability()
    monkeypatch.setattr(EX, "require_preflight_clearance", lambda *a, **k: None)
    result = EX.assemble_real_panel(ReaderTripwire("f", feats), ReaderTripwire("o", outs), auth)
    acc = result["accounting"]
    assert acc[ARP.STATE_ZERO_FILLED] == 3
    assert sum(acc[s] for s in ARP.FEATURE_ROW_STATES) == len(feats)
    zeros = result["outcomes"][result["outcomes"]["outcome_state"] == ARP.STATE_ZERO_FILLED]
    assert (zeros[ARP.OUTCOME_COLUMN] == 0.0).all()

    direct = ARP.assemble_panel_core(feats, outs)
    assert direct["accounting"] == acc, "the door changed production semantics"


def test_the_door_returns_exactly_what_assemble_panel_core_returns(monkeypatch):
    feats = _synthetic_features()
    outs = _synthetic_outcomes(feats)
    auth = _capability()
    monkeypatch.setattr(EX, "require_preflight_clearance", lambda *a, **k: None)
    via_door = EX.assemble_real_panel(ReaderTripwire("f", feats), ReaderTripwire("o", outs), auth)
    direct = ARP.assemble_panel_core(feats, outs)
    pd.testing.assert_frame_equal(via_door["features"], direct["features"])
    pd.testing.assert_frame_equal(via_door["outcomes"], direct["outcomes"])


def test_the_authorized_readers_are_the_documented_way_to_build_them(tmp_path):
    """Constructing them reads nothing; the pins are verified when they are CALLED.

    Exercised against a TEMP file so the canonical weekly snapshot is never opened.
    """
    reader = ARP.authorized_outcome_reader(path=tmp_path / "absent.parquet")
    with pytest.raises(ARP.AssemblyError):
        reader()
    assert ARP.default_outcome_reader is not ARP.authorized_outcome_reader
    with pytest.raises(ARP.AssemblyError):
        ARP.default_outcome_reader()


# =====================================================================================================
# Design B stays oracle and unselectable; the pinned inputs are all four
# =====================================================================================================
def test_design_b_remains_oracle_and_unselectable():
    pf = EX.preflight(phase=EX.PREFLIGHT_PHASE_PRE_RUN)
    assert pf["checks"]["design_b_oracle_and_unselectable"]["ok"] is True
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    body = src.split("def run_experiment", 1)[1].split("\ndef ", 1)[0]
    selection = body.split("):", 1)[1].split("if coach_b is not None", 1)[0]
    assert "coach_b" not in selection, "Design B reached the selection path"


def test_the_door_did_not_introduce_a_design_b_path():
    src = ast.dump(_door())
    assert "coach_b" not in src and "design_b" not in src


def test_all_four_pinned_input_families_are_verified_before_reading():
    """veteran features, rookie matrix, weekly outcome — plus coaching via preflight."""
    assert ARP.verify_pinned_activation_inputs(strict=False) == []
    pf = EX.preflight(phase=EX.PREFLIGHT_PHASE_PRE_RUN)
    assert pf["checks"]["v39_artifacts_pinned"]["ok"] is True, "coaching artifacts are the 4th family"


@pytest.mark.parametrize("attr,bad", [("VETERAN_SNAPSHOT_SHA256", "0" * 64),
                                      ("WEEKLY_SNAPSHOT_SHA256", "0" * 64),
                                      ("ROOKIE_MATRIX_SHA256", "0" * 64)])
def test_each_pinned_input_family_fails_closed_independently(monkeypatch, attr, bad):
    monkeypatch.setattr(ARP, attr, bad)
    with pytest.raises(ARP.AssemblyError):
        ARP.verify_pinned_activation_inputs()


# =====================================================================================================
# The stop state
# =====================================================================================================
def test_the_stop_state_is_exactly_what_was_asked_for():
    pf = EX.preflight(pipeline_assertions={k: 3 for k in EX._PIPELINE_ASSERTIONS})
    assert pf["all_ok"] is True and pf["n_checks"] == 21 and pf["n_failed"] == 0
    assert ARP.activation_readiness()[0] is True
    gate_ok, detail = ARP.authorized_real_gate(pf)
    assert gate_ok is False
    assert "BOTH LOCKS CLOSED" in detail
    assert "gate 2" not in detail, "gate 2 must be clear; only the locks hold the run back"
    assert EX.REAL_FIT_AUTHORIZED is False
    assert EX.real_fit_lock_state() == (False, False)


def test_no_result_artifact_was_written():
    pf = EX.preflight(phase=EX.PREFLIGHT_PHASE_PRE_RUN)
    for check in ("no_unauthorized_v39_artifact", "v39_artifacts_pinned", "protected_hashes",
                  "production_models_identical", "no_coaching_parquet"):
        assert pf["checks"][check]["ok"] is True, pf["checks"][check]["detail"]


def test_this_module_never_opens_the_canonical_outcome_snapshot():
    """Self-scan: no test here names the weekly snapshot or calls a real outcome reader unstubbed."""
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    # the needle is ASSEMBLED at runtime; spelling it as one literal would make this test match
    # its own source — the self-matching-guard defect this project has hit three times.
    needle = "player" + "_stats_" + "2011_2025"
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings and needle in n.value]
    assert not hits, f"this module names the canonical outcome snapshot at line(s) {hits}"
    assert ("authorized_outcome_reader" + "()()") not in src
