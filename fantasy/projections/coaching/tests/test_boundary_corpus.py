"""Red/green proof for the no-real-outcome boundary, asserted rather than narrated.

Every previous pass reported "N injections passed before, 0 now" from a scratchpad script. That number
was never checkable: no test materialised the historical validator, and counting `test_c5*`-style nodes
mixed injections with positive controls. This module fixes both. The corpus is enumerated once in
`boundary_corpus.py` with a stable id per case; the validator committed at `HISTORICAL_REV` is
materialised with `git show` into a temp directory; and the red/green totals are asserted from the table.

Canonical source is never modified — every case is a pure in-memory string.
"""
import hashlib
import importlib.util
import pathlib
import subprocess
import sys
import tempfile

import pytest

import boundary_corpus as CORPUS_MOD
from boundary_corpus import (CORPUS, POSITIVE_CONTROLS, HISTORICAL_REV, HARNESS,
                             HISTORICAL_COMMIT, HISTORICAL_BLOB, HISTORICAL_PATH,
                             HISTORICAL_FIXTURE, HISTORICAL_SHA256,
                             case_sources, control_sources, totals)

COACH = pathlib.Path(__file__).resolve().parent.parent
REPO = COACH.parent.parent.parent
REL = "fantasy/projections/coaching/run_coach_projection_experiment_v39.py"

sys.path.insert(0, str(COACH))
import run_coach_projection_experiment_v39 as EX          # noqa: E402  the CURRENT validator


@pytest.fixture(scope="module")
def historical():
    """The validator exactly as committed at HISTORICAL_REV, from the REPO-OWNED frozen fixture.

    This used to `git show` the revision and `pytest.skip` when git was missing or the commit was
    unreachable — which meant a fully green suite was possible with the red proof never executed. A
    proof that can silently not run is not a proof. The source is now vendored in the repo, pinned by
    sha256, and loaded with no git, no network and no history required; every failure path below is an
    assertion, never a skip.
    """
    fixture = (COACH / "tests" / HISTORICAL_FIXTURE).resolve()
    assert fixture.exists(), (
        f"the frozen historical validator is missing: {fixture}. The red proof cannot be skipped; "
        f"restore it with `git show {HISTORICAL_COMMIT}:{HISTORICAL_PATH}`.")

    raw = fixture.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == HISTORICAL_SHA256, (
        f"the frozen historical validator has been modified.\n  expected sha256 {HISTORICAL_SHA256}\n"
        f"  actual   sha256 {digest}\nIt is a historical artifact and must never be edited.")

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="v39_hist_"))
    path = tmp / "historical_harness_v39.py"
    path.write_bytes(raw)
    spec = importlib.util.spec_from_file_location("historical_harness_v39", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["historical_harness_v39"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_frozen_fixture_is_pinned_and_present():
    """Fail closed: the pin itself is a test, not a precondition of one."""
    fixture = (COACH / "tests" / HISTORICAL_FIXTURE).resolve()
    assert fixture.exists(), f"missing frozen historical validator: {fixture}"
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert digest == HISTORICAL_SHA256
    assert HISTORICAL_COMMIT.startswith(HISTORICAL_REV)
    assert len(HISTORICAL_BLOB) == 40 and len(HISTORICAL_COMMIT) == 40


def test_the_frozen_fixture_still_matches_the_pinned_revision_when_git_is_available():
    """Cross-check only. If git is absent this check is skipped — the RED PROOF above is not.

    The proof runs from the vendored bytes regardless; this merely confirms those bytes are still what
    `a5b4af7` holds, catching a fixture that was regenerated from the wrong revision.
    """
    try:
        proc = subprocess.run(["git", "cat-file", "-p", HISTORICAL_BLOB], cwd=REPO,
                              capture_output=True, text=True, encoding="utf-8")
    except OSError as exc:
        pytest.skip(f"git unavailable for the cross-check: {exc}")
    if proc.returncode != 0:
        pytest.skip(f"blob {HISTORICAL_BLOB[:12]} unreachable: {proc.stderr.strip()[:100]}")
    fixture = (COACH / "tests" / HISTORICAL_FIXTURE).resolve()
    assert proc.stdout == fixture.read_text(encoding="utf-8"), (
        "the vendored fixture no longer matches the pinned blob")


def _verdict(mod, sources):
    ok, detail = mod.no_real_outcome_access(sources=sources)
    assert isinstance(ok, bool), f"validator returned {ok!r}, not a bool"
    return ok, detail


# =====================================================================================================
# The corpus itself must stay well-formed
# =====================================================================================================
def test_the_corpus_has_unique_ids_and_known_categories():
    ids = [c[0] for c in CORPUS]
    assert len(ids) == len(set(ids)), "duplicate case id in the corpus"
    for cid, cat, kind, module, _payload, hist in CORPUS:
        assert cat in CORPUS_MOD.CATEGORIES, f"{cid}: unknown category {cat}"
        assert kind in ("append", "replace_entry_point", "drop_module", "extra_module"), cid
        assert isinstance(hist, bool), f"{cid}: historical_undetected must be a bool"


def test_the_corpus_contains_the_standalone_augmented_assignment_case():
    """The earlier fixture wrote `= None` first, so the plain Assign did the catching."""
    case = next(c for c in CORPUS if c[0] == "c5-rebind-augassign-standalone")
    assert case[4].strip() == "assemble_real_panel += 1"


def test_positive_controls_are_not_counted_as_injections():
    """A control is not an evasion; conflating them is how a wrong 'N cases' figure appears."""
    injection_ids = {c[0] for c in CORPUS}
    for cid, *_ in POSITIVE_CONTROLS:
        assert cid not in injection_ids
        assert cid.startswith("ctl-")


# =====================================================================================================
# GREEN — the current validator catches every injection and clears every control
# =====================================================================================================
@pytest.mark.parametrize("case", CORPUS, ids=[c[0] for c in CORPUS])
def test_the_current_validator_catches_every_injection(case):
    ok, detail = _verdict(EX, case_sources(case))
    assert ok is False, f"{case[0]} ({case[1]}) is NOT detected by the current validator"


@pytest.mark.parametrize("control", POSITIVE_CONTROLS, ids=[c[0] for c in POSITIVE_CONTROLS])
def test_the_current_validator_clears_every_positive_control(control):
    ok, detail = _verdict(EX, control_sources(control))
    assert ok is True, f"{control[0]} ({control[1]}) is a FALSE POSITIVE: {detail}"


# =====================================================================================================
# RED — the historical validator behaves exactly as the table records
# =====================================================================================================
@pytest.mark.parametrize("case", CORPUS, ids=[c[0] for c in CORPUS])
def test_the_historical_validator_matches_the_recorded_result(historical, case):
    cid, cat, _k, _m, _p, expected_undetected = case
    ok, _detail = _verdict(historical, case_sources(case, historical=True))
    assert ok is expected_undetected, (
        f"{cid} ({cat}): {HISTORICAL_REV} was recorded as "
        f"{'UNDETECTED' if expected_undetected else 'caught'} but returned ok={ok}")


def test_the_red_green_totals_are_exactly_as_reported(historical):
    """The single arithmetic any report may quote, computed from the table and re-measured here."""
    per, tot_undetected, n_cases = totals()

    measured_hist = sum(1 for c in CORPUS
                        if _verdict(historical, case_sources(c, historical=True))[0] is True)
    measured_now = sum(1 for c in CORPUS if _verdict(EX, case_sources(c))[0] is True)

    assert measured_hist == tot_undetected, (
        f"table says {tot_undetected} undetected at {HISTORICAL_REV}, measured {measured_hist}")
    assert measured_now == 0, f"{measured_now} injection(s) still undetected by the current validator"

    # the numbers a document is allowed to quote; summed over the DECLARED categories, not a
    # hand-written list that silently drops one when a category is added
    assert n_cases == len(CORPUS)
    assert sum(per[c][1] for c in CORPUS_MOD.CATEGORIES) == n_cases
    assert sum(per[c][0] for c in CORPUS_MOD.CATEGORIES) == tot_undetected


def test_the_reported_arithmetic_appears_in_the_stop_report():
    """Every number the report quotes must be one this corpus proves — and every category, not a subset.

    Expected strings are GENERATED from `totals()`. Nothing here restates a value by hand, so a corpus
    change cannot leave the document quietly stale: it fails this test until the document is updated.
    """
    per, tot_undetected, n_cases = totals()
    report = (COACH / "V39_PREFIT_STOP_REPORT.md").read_text(encoding="utf-8")

    missing = []
    for cat in CORPUS_MOD.CATEGORIES:
        assert cat in per, f"corpus has no cases in category {cat}, but it is declared in CATEGORIES"
        undetected, n = per[cat]
        if f"{cat} {undetected}/{n}" not in report:
            missing.append(f"{cat} {undetected}/{n}")

    historical_total = f"{tot_undetected} of {n_cases} injections passed undetected"
    current_total = f"0 of {n_cases}"
    if historical_total not in report:
        missing.append(historical_total)
    if current_total not in report:
        missing.append(current_total)

    assert not missing, ("the stop report must state these corpus figures verbatim:\n  "
                         + "\n  ".join(missing))


def test_every_declared_category_is_exercised_by_the_corpus():
    """A category in CATEGORIES with no cases would silently weaken the ledger."""
    per, _tot, _n = totals()
    for cat in CORPUS_MOD.CATEGORIES:
        assert per.get(cat, (0, 0))[1] > 0, f"category {cat} has no corpus cases"
    for cat in per:
        assert cat in CORPUS_MOD.CATEGORIES, f"corpus uses undeclared category {cat}"


def test_the_banned_callee_case_is_categorised_as_c3_not_c4():
    """C3 is the banned-CALLEE clause; C4 is the banned-TOKEN clause. They are different checks."""
    case = next(c for c in CORPUS if c[0] == "c3-banned-callee")
    assert case[1] == "C3"
    assert "season_total_target()" in case[4]
    assert not any(c[1] == "C3" and c[0] != "c3-banned-callee" for c in CORPUS)
