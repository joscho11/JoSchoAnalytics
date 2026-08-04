"""BUILD-CODE determinism: prove the BUILDER reproduces, not just the bytes.

The gap this closes
-------------------
`test_phase2.py::test_model_determinism_two_builds_identical` compares two
COMMITTED pickles (MODEL_ruled.pkl vs MODEL_ruled2.pkl). Both were produced by a
build that ran on Joseph's machine in July. That test proves the committed bytes
are stable. It cannot fail because of anything the builder does today -- if
`model.sig` grew an unseeded RNG tomorrow, those two fixtures would still match
each other and the suite would stay green.

This module drives the REAL build code instead:

    build_talent_score.stage_model('reproduce')  -> MODEL_reproduce.pkl
    build_talent_score.stage_board('reproduce')  -> BOARD_reproduce.pkl
    build_talent_score.stage_model('ruled')      -> MODEL_ruled.pkl

executed as `python build_talent_score.py <stage> <mode>` in two SEPARATE
scratch dirs (TALENT_WORK), from one synthetic pre-build INPUT fixture
(`tests/fixtures/synth_facets.py`). Those three stages transitively execute
`model.fit`, `model._design`, `model.sig`, `model.sigma2_eps`,
`model.facet_stats`, `model.sig_mom`, `model.s2eps_mom`, `composite.build_boards`,
`composite.eff_shares`, `composite.scored_universe` and
`schemas.stable_rank_sort` -- the actual transformation stack, not a
reimplementation of it.

What is NOT covered here, precisely
-----------------------------------
* `facets.build_inputs()` -- the ingest stage. It pulls nflreadpy live and reads
  the seasonal CSVs; it cannot run offline and its output IS the fixture's
  shape. Ingest determinism is therefore UNPROVEN by this module.
* `stage_board('ruled')` -- it hard-reads `C:/tmp/RHO2.pkl` (the RB college pipe)
  from an absolute machine-local path, so the ruled board path and the RB-pipe
  branch of `build_boards` are only exercised by the manual real-input gate at
  the bottom of this file, never in CI.
* `stage_emit()` -- deliberately never run: it writes the shipped
  `talent_score_2026.csv`.
* Real, licensed inputs. See `test_real_input_rebuild_*` (env-gated).
"""
import hashlib
import os
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

from synth_facets import (build_synth_facets, digest_facets,      # noqa: E402
                          write_synth_facets, _frame_digest)
from schemas import stable_rank_sort                              # noqa: E402

# Pinned fingerprint of the synthetic INPUT fixture. If the generator ever
# stops being deterministic (or is edited), this moves and the pin fails --
# a determinism proof driven by a drifting input proves nothing.
PINNED_INPUT_DIGEST = "4d9c3e2651940c2a0f2cbcc6a625d5cdf6a64d488235e66e11b02ec6d0349314"

STAGES = (("model", "reproduce"), ("board", "reproduce"), ("model", "ruled"))
OUTPUTS = ("MODEL_reproduce.pkl", "BOARD_reproduce.pkl", "MODEL_ruled.pkl")


# ---- driving the real build ----------------------------------------------------

def run_real_build(work: Path, shuffle_seed=None, stages=STAGES) -> Path:
    """Write the synthetic input into `work`, then run the REAL build stages
    there via `python build_talent_score.py <stage> <mode>`. Returns `work`."""
    work = Path(work)
    write_synth_facets(work, shuffle_seed=shuffle_seed)
    env = dict(os.environ, TALENT_WORK=str(work), PYTHONHASHSEED="0")
    for stage, mode in stages:
        r = subprocess.run([sys.executable, "build_talent_score.py", stage, mode],
                           cwd=str(PKG), env=env, capture_output=True, text=True)
        if r.returncode != 0:
            pytest.fail(f"real build stage `{stage} {mode}` failed in {work}:\n"
                        f"--- stdout ---\n{r.stdout[-3000:]}\n"
                        f"--- stderr ---\n{r.stderr[-3000:]}")
    return work


# ---- canonical digests ---------------------------------------------------------

def _obj_digest(o) -> str:
    """Canonical digest of the nested checkpoint payloads (dicts of frames,
    dicts of floats). Ordering-insensitive over dict keys, value/dtype/shape
    sensitive over frames."""
    if isinstance(o, (pd.DataFrame,)):
        return "F:" + _frame_digest(o)
    if isinstance(o, pd.Series):
        return "S:" + _frame_digest(o.to_frame("v"))
    if isinstance(o, dict):
        return "{" + ";".join(f"{k!r}={_obj_digest(o[k])}"
                              for k in sorted(o, key=repr)) + "}"
    if isinstance(o, (list, tuple)):
        return "[" + ";".join(_obj_digest(x) for x in o) + "]"
    if isinstance(o, (float, np.floating)):
        return f"{float(o):.12g}"
    if isinstance(o, (bool, np.bool_)):
        return f"bool:{bool(o)}"
    if isinstance(o, (int, np.integer)):
        return f"int:{int(o)}"
    return repr(o)


def ckpt_digest(path: Path) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(_obj_digest(pickle.load(fh)).encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---- THE comparator (shared by the green tests and the red proof) --------------

def assert_checkpoints_equivalent(p1: Path, p2: Path, label: str) -> None:
    """Raise AssertionError unless two build checkpoints are equivalent.

    Level 1 SEMANTIC: every DataFrame compared with pandas' own
      assert_frame_equal after sorting rows by index and columns by name, so
      the comparison is ordering-insensitive but values/dtypes/shape-sensitive.
    Level 2 SCALARS: every non-frame leaf (sigma^2_alpha stats, derived k,
      sigma^2_eps, eff shares, anchors, cfg) compared exactly.
    Level 3 CANONICAL: sha256 over the canonical serialization of the whole
      payload -- catches anything levels 1-2 forgot to walk.

    This same function is what the mutation test proves can go RED.
    """
    with open(p1, "rb") as fh:
        A = pickle.load(fh)
    with open(p2, "rb") as fh:
        B = pickle.load(fh)

    assert sorted(A, key=repr) == sorted(B, key=repr), \
        f"{label}: top-level keys differ: {sorted(A, key=repr)} vs {sorted(B, key=repr)}"

    frames = []

    def walk(a, b, path):
        if isinstance(a, pd.DataFrame) or isinstance(b, pd.DataFrame):
            assert isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame), \
                f"{label}{path}: one side is a DataFrame, the other is not"
            frames.append(path)
            x = a.sort_index(kind="mergesort").reindex(sorted(a.columns), axis=1)
            y = b.sort_index(kind="mergesort").reindex(sorted(b.columns), axis=1)
            pd.testing.assert_frame_equal(x, y, obj=f"{label}{path}",
                                          check_index_type=False)
        elif isinstance(a, dict) or isinstance(b, dict):
            assert isinstance(a, dict) and isinstance(b, dict), \
                f"{label}{path}: dict/non-dict mismatch"
            assert sorted(a, key=repr) == sorted(b, key=repr), \
                f"{label}{path}: keys differ"
            for k in sorted(a, key=repr):
                walk(a[k], b[k], f"{path}[{k!r}]")
        elif isinstance(a, pd.Series) or isinstance(b, pd.Series):
            pd.testing.assert_series_equal(a.sort_index(kind="mergesort"),
                                           b.sort_index(kind="mergesort"),
                                           obj=f"{label}{path}",
                                           check_index_type=False)
        else:
            assert _obj_digest(a) == _obj_digest(b), \
                f"{label}{path}: {a!r} != {b!r}"

    walk(A, B, "")
    assert frames, f"{label}: comparator walked ZERO DataFrames — it is vacuous"

    d1, d2 = ckpt_digest(p1), ckpt_digest(p2)
    assert d1 == d2, f"{label}: canonical digest differs\n  {d1}\n  {d2}"


# ---- session fixtures: the two independent real builds -------------------------

@pytest.fixture(scope="session")
def run_a(tmp_path_factory):
    return run_real_build(tmp_path_factory.mktemp("build_a"))


@pytest.fixture(scope="session")
def run_b(tmp_path_factory):
    return run_real_build(tmp_path_factory.mktemp("build_b"))


@pytest.fixture(scope="session")
def run_mutated(tmp_path_factory):
    """Same inputs, ROW ORDER PERMUTED. Values and dtypes are untouched."""
    return run_real_build(tmp_path_factory.mktemp("build_mut"), shuffle_seed=99)


# ---- 1. the input fixture is itself deterministic -------------------------------

def test_synthetic_input_fixture_is_deterministic_and_pinned():
    d1 = digest_facets(build_synth_facets())
    d2 = digest_facets(build_synth_facets())
    assert d1 == d2, "the synthetic input generator is not deterministic"
    assert d1 == PINNED_INPUT_DIGEST, (
        f"synthetic input fixture drifted: {d1} != pinned {PINNED_INPUT_DIGEST}. "
        f"Every determinism claim below is measured against this exact input; "
        f"re-pin only with an explained change.")


def test_synthetic_input_carries_no_real_identifiers():
    """Licensing guard: the committed fixture must be synthetic, not derived."""
    fac = build_synth_facets()
    ids = set(fac["nfl_ids"])
    assert ids, "fixture has no ids"
    assert all(i.startswith("SYN-") for i in ids), "non-synthetic id in the fixture"
    # real gsis ids look like 00-0034796; assert none can be present
    assert not any(pd.Series(sorted(ids)).str.match(r"^\d{2}-\d{7}$")), \
        "a gsis-shaped id leaked into the synthetic fixture"
    assert all(n.startswith("Synth ") for n in fac["names"].values())
    # the generator must MANUFACTURE its data, never read any of it
    src = (Path(__file__).parent / "fixtures" / "synth_facets.py").read_text()
    for banned in ("read_csv", "read_parquet", "nflreadpy", "import nfl",
                   "requests", "urllib"):
        assert banned not in src, f"synthetic generator reads data: {banned!r}"


# ---- 2. two independent real builds agree ---------------------------------------

@pytest.mark.parametrize("name", OUTPUTS)
def test_two_real_builds_are_semantically_identical(run_a, run_b, name):
    assert_checkpoints_equivalent(run_a / name, run_b / name, name)


@pytest.mark.parametrize("name", OUTPUTS)
def test_two_real_builds_are_byte_identical(run_a, run_b, name):
    """Stronger than the semantic check: the serialized checkpoints match byte
    for byte across two processes in two directories."""
    h1, h2 = sha256_file(run_a / name), sha256_file(run_b / name)
    assert h1 == h2, f"{name} pickle bytes differ:\n  run A {h1}\n  run B {h2}"


def test_two_real_builds_input_was_identical(run_a, run_b):
    """Guards the whole comparison: if the two runs got different inputs, the
    output agreement above would be meaningless."""
    assert sha256_file(run_a / "FACETS.pkl") == sha256_file(run_b / "FACETS.pkl")


def test_the_real_build_actually_ran(run_a):
    """A determinism test over two files nobody wrote is vacuous."""
    for name in OUTPUTS:
        p = run_a / name
        assert p.exists() and p.stat().st_size > 1000, f"{name} was not produced"
    M = pickle.load(open(run_a / "MODEL_ruled.pkl", "rb"))
    assert M["cfg"]["K_MODE"] == "derived" and M["cfg"]["NS"] == 60
    assert set(M["F"]) == {"RB", "WR", "TE", "QB"}
    assert M["S2E"], "ruled build produced no derived sigma^2_eps — k path not exercised"
    B = pickle.load(open(run_a / "BOARD_reproduce.pkl", "rb"))
    assert set(B["boards"]) == {"RB", "WR", "TE", "QB"}
    for P, sh in B["shares"].items():
        assert abs(sum(sh.values()) - 1.0) < 1e-9, P


# ---- 3. MUTATION: prove the comparator can go RED --------------------------------

def test_RED_row_order_mutation_breaks_model_determinism(run_a, run_b, run_mutated):
    """RED PROOF. Feed the SAME rows in a different ORDER and the comparator
    used by every green test above must FAIL. `model.sig` / `model.sig_mom`
    assign split halves with `rng.random(len(d)) < 0.5`, which is positional.

    Green and red are asserted side by side, with the same comparator, so a
    comparator that had quietly become incapable of failing is caught here.

    Measured 2026-08-03 (shuffle_seed=99): the raise lands on a real frame
    value -- `MODEL_ruled.pkl['F']['QB']['bad']` column "w", 100.0% of rows
    different -- max relative move in derived k = 0.1235 (RB/brkTkl_rec
    87.33 -> 98.11), max |dw| = 0.0283.
    """
    # green side: the identical-input pair must NOT raise
    assert_checkpoints_equivalent(run_a / "MODEL_ruled.pkl",
                                  run_b / "MODEL_ruled.pkl", "control")

    with pytest.raises(AssertionError) as exc:
        assert_checkpoints_equivalent(run_a / "MODEL_ruled.pkl",
                                      run_mutated / "MODEL_ruled.pkl",
                                      "MODEL_ruled.pkl")
    msg = str(exc.value)
    assert "MODEL_ruled.pkl['F']" in msg and "are different" in msg, (
        "the red proof raised, but not on a build VALUE — it may be failing for "
        f"an unrelated reason:\n{msg[:800]}")

    # quantify the perturbation so the red is measured, not merely asserted
    A = pickle.load(open(run_a / "MODEL_ruled.pkl", "rb"))
    Mu = pickle.load(open(run_mutated / "MODEL_ruled.pkl", "rb"))
    rel_k = max(abs(A["K"][k] - Mu["K"][k]) / max(abs(A["K"][k]), 1e-12)
                for k in A["K"])
    max_dw = max(float(np.abs(A["F"][P][f]["w"].values
                              - Mu["F"][P][f]["w"].reindex(A["F"][P][f].index).values).max())
                 for P in A["F"] for f in A["F"][P])
    assert rel_k > 1e-3, f"row-order mutation moved k by only {rel_k:.3e} (relative)"
    assert max_dw > 1e-4, f"row-order mutation moved w by only {max_dw:.3e}"
    assert ckpt_digest(run_a / "MODEL_ruled.pkl") != \
        ckpt_digest(run_mutated / "MODEL_ruled.pkl")


def test_RED_row_order_mutation_breaks_board_determinism(run_a, run_b, run_mutated):
    """The same mutation must also break the BOARD comparator, and must move
    real player SCORES and RANKS -- not just an invisible internal.

    Measured 2026-08-03: max |delta score| RB 7.79 / WR 9.07 / TE 9.00 points,
    rank_pos changed for 39/45 RB, 34/45 WR, 28/30 TE. QB moves 0.00 in this
    checkpoint and that is correct, not a miss: reproduce-mode QB is the legacy
    career-value branch, which never touches the positional split-half RNG.
    """
    assert_checkpoints_equivalent(run_a / "BOARD_reproduce.pkl",
                                  run_b / "BOARD_reproduce.pkl", "control")
    with pytest.raises(AssertionError):
        assert_checkpoints_equivalent(run_a / "BOARD_reproduce.pkl",
                                      run_mutated / "BOARD_reproduce.pkl",
                                      "BOARD_reproduce.pkl")
    A = pickle.load(open(run_a / "BOARD_reproduce.pkl", "rb"))
    Mu = pickle.load(open(run_mutated / "BOARD_reproduce.pkl", "rb"))
    moved, reranked = {}, {}
    for P in A["boards"]:
        a = A["boards"][P]
        m = Mu["boards"][P].reindex(a.index)
        moved[P] = float(np.abs(a["score"].values - m["score"].values).max())
        reranked[P] = int((a["rank_pos"].values != m["rank_pos"].values).sum())
    assert max(moved.values()) > 1.0, f"board scores barely moved: {moved}"
    assert max(reranked.values()) > 5, f"board order barely moved: {reranked}"


SPLIT_RNG_LINE = "h = rng.random(len(d)) < 0.5"


def test_RED_unseeded_rng_in_the_builder_breaks_determinism(tmp_path):
    """RED PROOF, strongest form: mutate the BUILDER, not the input.

    A COPY of the talent package is made in a tmp dir and `model.sig`'s seeded
    split-half draw is replaced with an unseeded one -- exactly the regression
    the committed output fixtures cannot detect, since MODEL_ruled.pkl and
    MODEL_ruled2.pkl would still equal each other. Two builds are then run off
    the mutated copy and the comparator must fail.

    The repo copy of model.py is never modified; the mutation lives only in
    `tmp_path`. Measured 2026-08-03: raises on
    MODEL_ruled['F']['RB']['YACcon'] column "w", 100.0% of rows different.
    """
    real_model = (PKG / "model.py").read_text()
    assert SPLIT_RNG_LINE in real_model, (
        f"model.py no longer contains {SPLIT_RNG_LINE!r} — this mutation test "
        f"would silently mutate nothing. Update it to the current seeded draw.")

    mut = tmp_path / "pkg"
    mut.mkdir()
    for p in PKG.glob("*.py"):
        (mut / p.name).write_text(p.read_text())
    (mut / "model.py").write_text(real_model.replace(
        SPLIT_RNG_LINE, "h = np.random.default_rng().random(len(d)) < 0.5"))

    outs = []
    for tag in ("m1", "m2"):
        d = tmp_path / tag
        write_synth_facets(d)
        env = dict(os.environ, TALENT_WORK=str(d), PYTHONHASHSEED="0")
        r = subprocess.run([sys.executable, "build_talent_score.py", "model", "ruled"],
                           cwd=str(mut), env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-3000:]
        outs.append(d / "MODEL_ruled.pkl")

    assert sha256_file(outs[0]) != sha256_file(outs[1]), \
        "the unseeded-RNG mutation produced identical bytes — it was inert"
    with pytest.raises(AssertionError) as exc:
        assert_checkpoints_equivalent(outs[0], outs[1], "MUTATED")
    assert "MUTATED['F']" in str(exc.value) and "are different" in str(exc.value)
    # the repo's own model.py must be untouched by this test
    assert (PKG / "model.py").read_text() == real_model


def test_RED_unstable_sort_breaks_board_order_but_stable_rank_sort_does_not():
    """RED PROOF for the ordering/dedupe half: on TIED (score, w) rows a naive
    sort is input-order dependent; `schemas.stable_rank_sort`'s gsis tiebreak
    is not. Ties are constructed here because the synthetic board has none."""
    S = pd.DataFrame({"score": [80.0, 80.0, 80.0, 71.0], "w": [0.5, 0.5, 0.5, 0.9]},
                     index=["00-0000004", "00-0000002", "00-0000009", "00-0000007"])
    perm = S.iloc[[2, 0, 3, 1]]

    def naive(d):
        return d.sort_values(["score", "w"], ascending=[False, False],
                             kind="quicksort")

    assert list(naive(S).index) != list(naive(perm).index), \
        "the mutation is inert here — the naive sorter happened to agree"
    assert list(stable_rank_sort(S).index) == list(stable_rank_sort(perm).index)
    assert list(stable_rank_sort(S)["rank_pos"]) == [1, 2, 3, 4]


# ---- 4. PROTECTED / MANUAL real-input rebuild gate --------------------------------

REAL_GATE_ENV = "TALENT_REAL_REBUILD"
REAL_FACETS_ENV = "TALENT_REAL_FACETS"
DEFAULT_REAL_FACETS = "C:/tmp/talent_build/FACETS.pkl"

REAL_GATE_LIMITATION = """
LIMITATION, stated precisely.

Everything above runs on a SYNTHETIC input. It proves the builder is a
deterministic function of its input on this machine and in this environment. It
does NOT prove that a rebuild from the REAL inputs reproduces the shipped
`talent_score_2026.csv` or the committed MODEL/BOARD fixtures, because the real
inputs (licensed PFF-adjacent feeds via nflreadpy, the seasonal CSVs, and
C:/tmp/RHO2.pkl) are not in the repo and cannot be committed. No output-only
fixture can establish that either.

This gate is the only test in the package that can. It is opt-in and never runs
in CI:

    TALENT_REAL_REBUILD=1 python -m pytest tests/test_build_determinism.py -k real -q

It copies a real FACETS.pkl (TALENT_REAL_FACETS, default C:/tmp/talent_build/
FACETS.pkl) into a pytest tmp dir, rebuilds `model ruled` there TWICE, and
compares the two rebuilds AND the committed fixture. It never writes to the
source dir, never runs `stage_emit`, and never touches a shipped artifact.
"""


def _real_gate_or_skip(tmp_path):
    if os.environ.get(REAL_GATE_ENV) != "1":
        pytest.skip(f"PROTECTED real-input rebuild: set {REAL_GATE_ENV}=1 to run. "
                    + REAL_GATE_LIMITATION)
    src = Path(os.environ.get(REAL_FACETS_ENV) or DEFAULT_REAL_FACETS)
    if not src.exists():
        pytest.fail(f"{REAL_GATE_ENV}=1 but the real input {src} is absent; point "
                    f"{REAL_FACETS_ENV} at a real FACETS.pkl.")
    return src


@pytest.mark.real_inputs
def test_real_input_rebuild_is_deterministic(tmp_path):
    """MANUAL: two rebuilds from the REAL FACETS.pkl must agree."""
    src = _real_gate_or_skip(tmp_path)
    dirs = []
    for tag in ("r1", "r2"):
        d = tmp_path / tag
        d.mkdir()
        (d / "FACETS.pkl").write_bytes(src.read_bytes())
        env = dict(os.environ, TALENT_WORK=str(d), PYTHONHASHSEED="0")
        r = subprocess.run([sys.executable, "build_talent_score.py", "model", "ruled"],
                           cwd=str(PKG), env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-3000:]
        dirs.append(d)
    assert_checkpoints_equivalent(dirs[0] / "MODEL_ruled.pkl",
                                  dirs[1] / "MODEL_ruled.pkl",
                                  "REAL MODEL_ruled.pkl")


@pytest.mark.real_inputs
def test_real_input_rebuild_reproduces_committed_fixture(tmp_path):
    """MANUAL: a rebuild from the REAL FACETS.pkl must reproduce the committed
    MODEL_ruled.pkl fixture the other 26 tests read.

    Compared SEMANTICALLY, not byte-wise, and that distinction is measured, not
    assumed: as of 2026-08-03 a fresh rebuild differs from the committed pickle
    in the pandas string dtype BACKING the frame index (`str`/pyarrow in the
    fixture vs `string`/python in a fresh env) while every value, every derived
    k, every sigma^2_eps and every sigma^2_alpha stat is bit-equal. That is an
    environment artefact of pandas' string-storage inference, not build drift,
    so the byte hashes are REPORTED (below) and the values are ASSERTED.
    """
    src = _real_gate_or_skip(tmp_path)
    d = tmp_path / "fresh"
    d.mkdir()
    (d / "FACETS.pkl").write_bytes(src.read_bytes())
    env = dict(os.environ, TALENT_WORK=str(d), PYTHONHASHSEED="0")
    r = subprocess.run([sys.executable, "build_talent_score.py", "model", "ruled"],
                       cwd=str(PKG), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-3000:]

    fixture = PKG / "tests" / "fixtures" / "work" / "MODEL_ruled.pkl"
    assert fixture.exists(), fixture
    assert_checkpoints_equivalent(d / "MODEL_ruled.pkl", fixture,
                                  "REAL rebuild vs committed fixture")
    print(f"[real-gate] fresh   sha256 {sha256_file(d / 'MODEL_ruled.pkl')}\n"
          f"[real-gate] fixture sha256 {sha256_file(fixture)}")
