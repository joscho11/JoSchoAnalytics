"""THE INVOCATION-SCOPED AUTHORIZATION CAPABILITY — the activation contradiction, repaired.

THE CONTRADICTION, found by reading the committed source at 8ca2efc and reproduced below:
  * C6 statically requires exactly one module-level `REAL_FIT_AUTHORIZED = False`;
  * `authorized_real` required that constant to be True at runtime;
  * editing the source to True made C6 — and therefore the 21-check preflight — FAIL;
  * the tests only reached the authorized path by monkeypatching the global, and the documented CLI
    had no equivalent mechanism.

So the published command could not open both locks by any route. The repair is a CAPABILITY:
`REAL_FIT_AUTHORIZED = False` stays in committed source as the default-closed invariant and is never
reassigned; authorization exists only as an immutable object minted per invocation from two exact
tokens and threaded explicitly through every gate.

NO LOCK IS OPENED HERE in the sense that matters: no real outcome is read, nothing is fit, and no
result is written. The token pair is exercised only against injected/stubbed readers.
"""
import ast
import pathlib
import subprocess
import sys

import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COACH))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import assemble_real_panel_v39 as ARP                      # noqa: E402
import run_coach_projection_experiment_v39 as EX           # noqa: E402

HARNESS = COACH / "run_coach_projection_experiment_v39.py"
BUILDER = COACH / "build_arm_features_v39.py"
CLI = EX.REAL_FIT_CLI_TOKEN
ENV = EX.REAL_FIT_ENV_TOKEN


def _auth():
    """The real token pair, in-process only. Mints a capability; opens nothing by itself."""
    return EX.grant_real_fit_authorization(CLI, env={EX.REAL_FIT_ENV_SWITCH: ENV})


# =====================================================================================================
# 1. THE CONTRADICTION, reproduced
# =====================================================================================================
def test_RED_editing_the_source_constant_to_True_FAILS_C6():
    """The route the manifest used to instruct. It breaks the very preflight it must pass."""
    src = HARNESS.read_text(encoding="utf-8")
    assert "REAL_FIT_AUTHORIZED = False" in src
    edited = src.replace("REAL_FIT_AUTHORIZED = False", "REAL_FIT_AUTHORIZED = True")
    ok, detail = EX.no_real_outcome_access(
        sources={"run_coach_projection_experiment_v39.py": edited,
                 "build_arm_features_v39.py": BUILDER.read_text(encoding="utf-8")})
    assert ok is False
    assert "only one module-level" in detail


def test_RED_leaving_the_source_False_refuses_authorized_real_without_a_capability():
    """The other horn: as committed, and with no capability, authorized_real refuses."""
    ok, detail = EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL)
    assert ok is False and "BOTH real-fit locks OPEN" in detail


# =====================================================================================================
# 2. The default-closed invariant survives
# =====================================================================================================
def test_the_committed_source_still_binds_the_constant_False():
    src = HARNESS.read_text(encoding="utf-8")
    bindings = [ln.strip() for ln in src.splitlines() if ln.startswith("REAL_FIT_AUTHORIZED")]
    assert bindings == ["REAL_FIT_AUTHORIZED = False"]
    assert EX.REAL_FIT_AUTHORIZED is False


def test_the_frozen_tokens_are_exact():
    assert EX.REAL_FIT_CLI_TOKEN == "JOSEPH-AUTHORIZED-V39-FIRST-REAL-RUN"
    assert EX.REAL_FIT_ENV_TOKEN == "I-HAVE-WRITTEN-THE-PREFIT-AMENDMENT"
    assert EX.REAL_FIT_ENV_SWITCH == "COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH"


def test_MUTATING_the_module_global_authorizes_NOTHING(monkeypatch):
    """The old monkeypatch route is dead: the constant is never consulted as an opener."""
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", True, raising=False)
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, ENV)
    assert EX.real_fit_lock_state() == (False, True)
    assert EX.real_fit_is_unlocked() is False
    assert EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL)[0] is False
    with pytest.raises(RuntimeError):
        EX.require_real_fit_authorization()


def test_C6_rejects_a_runtime_GLOBALS_mutation_of_the_lock():
    src = HARNESS.read_text(encoding="utf-8")
    injected = src + "\n\ndef _sneak():\n    globals()['REAL_FIT_AUTHORIZED'] = True\n"
    ok, detail = EX.no_real_outcome_access(
        sources={"run_coach_projection_experiment_v39.py": injected,
                 "build_arm_features_v39.py": BUILDER.read_text(encoding="utf-8")})
    assert ok is False and "mutate REAL_FIT_AUTHORIZED" in detail


def test_C6_rejects_a_runtime_SETATTR_mutation_of_the_lock():
    src = HARNESS.read_text(encoding="utf-8")
    injected = src + "\n\ndef _sneak2(m):\n    setattr(m, 'REAL_FIT_AUTHORIZED', True)\n"
    ok, detail = EX.no_real_outcome_access(
        sources={"run_coach_projection_experiment_v39.py": injected,
                 "build_arm_features_v39.py": BUILDER.read_text(encoding="utf-8")})
    assert ok is False and "mutate REAL_FIT_AUTHORIZED" in detail


def test_the_live_source_passes_C6_unchanged():
    assert EX.no_real_outcome_access()[0] is True


# =====================================================================================================
# 3. Token combinations
# =====================================================================================================
@pytest.mark.parametrize("label,cli,env", [
    ("neither token", None, None),
    ("CLI token alone", CLI, None),
    ("environment token alone", None, ENV),
    ("wrong CLI token", "NOPE", ENV),
    ("empty CLI token", "", ENV),
    ("wrong env token", CLI, "NOPE"),
    ("empty env token", CLI, ""),
    ("CLI token lowercased", CLI.lower(), ENV),
    ("env token lowercased", CLI, ENV.lower()),
])
def test_every_wrong_or_PARTIAL_token_pair_refuses(label, cli, env):
    env_map = {} if env is None else {EX.REAL_FIT_ENV_SWITCH: env}
    with pytest.raises(RuntimeError) as e:
        EX.grant_real_fit_authorization(cli, env=env_map)
    assert "authorization refused" in str(e.value), label


def test_the_CORRECT_pair_mints_a_valid_capability():
    a = _auth()
    assert isinstance(a, EX.RealFitAuthorization)
    assert a.is_valid() is True and a.lock_state == (True, True)
    assert EX.authorization_is_valid(a) is True
    assert EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL, authorization=a)[0] is True


def test_the_capability_is_IMMUTABLE():
    a = _auth()
    for attr in ("_cli_ok", "_env_ok"):
        with pytest.raises(AttributeError):
            setattr(a, attr, False)
        with pytest.raises(AttributeError):
            delattr(a, attr)
    assert a.lock_state == (True, True)


@pytest.mark.parametrize("forged", [None, object(), "JOSEPH-AUTHORIZED-V39-FIRST-REAL-RUN",
                                    True, 1, {"cli": True, "env": True}])
def test_a_FORGED_or_absent_capability_is_not_authorization(forged):
    assert EX.authorization_is_valid(forged) is False
    assert EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL, authorization=forged)[0] is False
    with pytest.raises(RuntimeError):
        EX.require_real_fit_authorization(forged)


def test_authorization_does_NOT_survive_into_a_second_invocation():
    """It is invocation-scoped: nothing about it is stored anywhere."""
    a = _auth()
    assert EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL, authorization=a)[0] is True
    del a
    assert EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL)[0] is False
    assert EX.real_fit_lock_state() == (False, EX.REAL_FIT_ENV_SWITCH in __import__("os").environ)
    assert EX.REAL_FIT_AUTHORIZED is False
    src = HARNESS.read_text(encoding="utf-8")
    assert "REAL_FIT_AUTHORIZED = False" in src and "REAL_FIT_AUTHORIZED = True" not in src


def test_no_module_global_holds_a_capability():
    held = [n for n, v in vars(EX).items() if isinstance(v, EX.RealFitAuthorization)]
    assert held == [], f"a capability is stored in a module global: {held}"


# =====================================================================================================
# 4. The gates refuse without the capability, and reach ZERO readers
# =====================================================================================================
def _tripwires():
    calls = []

    def make(name):
        def _r():
            calls.append(name)
            raise AssertionError(f"the {name} reader RAN")
        return _r
    return calls, make


@pytest.mark.parametrize("authorization", [None, object()])
def test_the_door_refuses_without_a_valid_capability_and_reaches_zero_readers(authorization):
    calls, make = _tripwires()
    with pytest.raises(RuntimeError):
        EX.assemble_real_panel(make("feature"), make("outcome"), authorization)
    assert calls == []


def test_run_authorized_real_refuses_without_a_capability(monkeypatch):
    reads = []
    monkeypatch.setattr(ARP, "authorized_composed_feature_reader",
                        lambda *a, **k: reads.append("f") or (lambda: None))
    monkeypatch.setattr(ARP, "authorized_outcome_reader",
                        lambda *a, **k: reads.append("o") or (lambda: None))
    with pytest.raises(RuntimeError):
        EX.run_authorized_real((2024,), 10, 2, verbose=False, authorization=None)
    assert reads == []


def test_require_preflight_clearance_refuses_without_a_capability():
    with pytest.raises(RuntimeError) as e:
        EX.require_preflight_clearance(EX.RUN_MODE_AUTHORIZED_REAL, authorization=None)
    assert "NOT AUTHORIZED" in str(e.value).upper()


# =====================================================================================================
# 5. The CLI
# =====================================================================================================
def test_the_CLI_exposes_the_authorization_token_flag():
    src = HARNESS.read_text(encoding="utf-8")
    assert '"--authorization-token"' in src
    assert "grant_real_fit_authorization(a.authorization_token)" in src


def test_the_DOCUMENTED_command_WITHOUT_the_CLI_token_refuses_before_readers(monkeypatch):
    """The exact previously-published invocation. It must refuse, and touch nothing."""
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, ENV)
    reads = []
    monkeypatch.setattr(ARP, "authorized_composed_feature_reader",
                        lambda *a, **k: reads.append("f") or (lambda: None))
    monkeypatch.setattr(sys, "argv", ["prog", "--run-mode", "authorized_real",
                                      "--outer-seasons", "2018-2025"])
    with pytest.raises(SystemExit) as e:
        EX.main()
    assert "BLOCKED" in str(e.value)
    assert reads == []


@pytest.mark.parametrize("argv_extra,set_env", [
    (["--authorization-token", CLI], False),          # CLI token alone
    ([], True),                                       # env token alone
    (["--authorization-token", "WRONG"], True),       # wrong CLI token
    (["--authorization-token", ""], True),            # empty CLI token
])
def test_partial_or_wrong_CLI_invocations_refuse_before_readers(monkeypatch, argv_extra, set_env):
    if set_env:
        monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, ENV)
    else:
        monkeypatch.delenv(EX.REAL_FIT_ENV_SWITCH, raising=False)
    reads = []
    monkeypatch.setattr(ARP, "authorized_composed_feature_reader",
                        lambda *a, **k: reads.append("f") or (lambda: None))
    monkeypatch.setattr(ARP, "authorized_outcome_reader",
                        lambda *a, **k: reads.append("o") or (lambda: None))
    monkeypatch.setattr(sys, "argv", ["prog", "--run-mode", "authorized_real",
                                      "--outer-seasons", "2018-2025"] + argv_extra)
    with pytest.raises(SystemExit) as e:
        EX.main()
    assert "BLOCKED" in str(e.value)
    assert reads == []


def test_the_CORRECT_pair_reaches_the_SYNTHETIC_INJECTED_authorized_path(monkeypatch):
    """The only place both tokens are presented together — and the run is fully injected.

    `run_authorized_real` is replaced, so no reader, no outcome and no result writer is reached.
    What is proven is that the CLI now HAS a route through authorization, which it previously lacked.
    """
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, ENV)
    reached = {}

    def _fake_run(seasons, boot, plac, out_dir=None, overwrite=False, verbose=True,
                 authorization=None):
        reached["seasons"] = tuple(seasons)
        reached["authorized"] = EX.authorization_is_valid(authorization)
        return {}, {"arm_verdict_v39.csv": "0" * 64}

    monkeypatch.setattr(EX, "run_authorized_real", _fake_run)
    monkeypatch.setattr(sys, "argv", ["prog", "--run-mode", "authorized_real",
                                      "--authorization-token", CLI,
                                      "--outer-seasons", "2018-2025"])
    EX.main()
    assert reached["seasons"] == tuple(range(2018, 2026))
    assert reached["authorized"] is True
    assert EX.REAL_FIT_AUTHORIZED is False


def test_the_exact_documented_command_appears_in_the_manifest():
    text = (COACH / "V39_ACTIVATION_MANIFEST.md").read_text(encoding="utf-8")
    assert "--authorization-token JOSEPH-AUTHORIZED-V39-FIRST-REAL-RUN" in text
    assert f"{EX.REAL_FIT_ENV_SWITCH}={ENV}" in text


def test_no_document_still_instructs_editing_the_constant_to_True():
    """The instruction that created the contradiction must be gone or explicitly retired."""
    for rel in ("V39_ACTIVATION_MANIFEST.md", "V39_PREFIT_STOP_REPORT.md",
                "../preregs/PREREG_coach_quality_2026-07-28.md"):
        text = (COACH / rel).read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "REAL_FIT_AUTHORIZED = True" in line or "REAL_FIT_AUTHORIZED` (module constant)" in line:
                assert any(q in line for q in ("SUPERSEDED", "WITHDRAWN", "CORRECTED",
                                                "used to read", "no longer", "never")), (
                    f"{rel}:{lineno} still instructs editing the constant: {line.strip()[:90]}")


# =====================================================================================================
# 6. C5-A still pins the door, now to the capability
# =====================================================================================================
def test_C5_A_requires_the_door_to_consume_its_OWN_authorization_parameter():
    tree = EX._executable_tree(HARNESS.read_text(encoding="utf-8"))
    assert EX._entry_point_is_sealed(tree, contract_mode=EX.RUN_MODE_AUTHORIZED_REAL) == []
    fn = next(n for n in ast.walk(ast.parse(HARNESS.read_text(encoding="utf-8")))
              if isinstance(n, ast.FunctionDef) and n.name == "assemble_real_panel")
    assert EX.AUTHORIZATION_PARAM in {a.arg for a in fn.args.args}
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    call = body[0].value
    assert call.func.id == "require_real_fit_authorization"
    assert len(call.args) == 1 and call.args[0].id == EX.AUTHORIZATION_PARAM


@pytest.mark.parametrize("bad_stmt", [
    "    require_real_fit_authorization()",
    "    require_real_fit_authorization(True)",
    "    require_real_fit_authorization(grant_real_fit_authorization('x'))",
    "    require_real_fit_authorization(REAL_FIT_AUTHORIZED)",
])
def test_C5_A_rejects_an_authorization_that_is_not_the_callers_capability(bad_stmt):
    import boundary_corpus as BC
    door = ("def assemble_real_panel(feature_reader, outcome_reader, authorization=None):\n"
            + bad_stmt + "\n"
            "    require_preflight_clearance()\n"
            "    return assemble_panel_core(feature_reader(), outcome_reader())")
    src = BC._replace_entry_point(HARNESS.read_text(encoding="utf-8"), door)
    problems = EX._entry_point_is_sealed(EX._executable_tree(src),
                                         contract_mode=EX.RUN_MODE_AUTHORIZED_REAL)
    assert problems and any("clause 1/6" in p for p in problems)


def test_the_binding_and_evasion_corpus_is_still_live():
    import boundary_corpus as BC
    assert len(BC.CORPUS) >= 75
    assert "C6" in BC.CATEGORIES and "C5" in BC.CATEGORIES and "C5A" in BC.CATEGORIES


# =====================================================================================================
# 7. The stop state, and the source after every test
# =====================================================================================================
def test_the_stop_state_is_unchanged():
    pf = EX.preflight(pipeline_assertions={k: 3 for k in EX._PIPELINE_ASSERTIONS})
    assert pf["all_ok"] is True and pf["n_checks"] == 21 and pf["n_failed"] == 0
    assert ARP.activation_readiness()[0] is True
    assert ARP.authorized_real_gate(pf)[0] is False
    assert EX.REAL_FIT_AUTHORIZED is False
    assert "REAL_FIT_AUTHORIZED = False" in HARNESS.read_text(encoding="utf-8")


def test_no_result_artifact_was_created():
    import write_v39_results as WR
    assert not (WR.RESULTS.exists() and list(WR.RESULTS.glob("*_v39.csv")))
