"""Walk-forward fold guards — real validation + the red proof for the tautology.

Defect (confirmed 2026-08-03): build_rb_projection.py guarded its walk-forward with

    tr = df[df.season < Y]; assert (tr.season < Y).all()
    a4 &= (vet[vet.season < Y].season < Y).all()

— filter a frame by a predicate, then test that same predicate on the result. The
expression is a tautology; it printed "PASS" while testing nothing. The same two
lines were copy-pasted into the WR, TE and QB builders. `test_old_guard_is_vacuous`
below re-materialises the old expression and proves it stays True on a pool with
50 injected target-season rows; `test_red_proof_*` proves the new guard raises on
exactly that frame.

Run:  pytest -q fantasy/projections/test_fold_guards.py
"""
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
# Point the module-level scratch at a throwaway dir BEFORE import: importing the
# engine mkdir()s it. Nothing else in this module touches the repo.
os.environ.setdefault("RB_SCRATCH", tempfile.mkdtemp(prefix="fold_guard_"))
sys.path.insert(0, str(HERE))

import build_rb_projection as B  # noqa: E402

TEST_SEASONS = B.TEST_SEASONS      # [2021..2025]
POOL_SEASONS = list(range(2017, 2026))


def make_pool(seed=0, n_per_season=40):
    """Synthetic (player_id, season, y, x) pool with a unique RangeIndex."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in POOL_SEASONS:
        for i in range(n_per_season):
            rows.append({"player_id": f"P{i:03d}", "season": s,
                         "y": float(rng.normal(150, 40)), "x": float(rng.normal())})
    return pd.DataFrame(rows).reset_index(drop=True)


# --------------------------------------------------------------------- happy path
def test_build_fold_exact_season_sets():
    df = make_pool()
    for Y in TEST_SEASONS:
        tr, te = B.build_fold(df, Y)
        assert set(tr.season.unique()) == {s for s in POOL_SEASONS if s < Y}
        assert set(te.season.unique()) == {Y}


def test_clean_fold_validates():
    df = make_pool()
    for Y in TEST_SEASONS:
        tr, te = B.build_fold(df, Y)
        rep = B.assert_walk_forward_fold(tr, te, Y, "unit", pool=df)
        assert rep["season"] == Y and rep["n_test"] > 0
        assert max(rep["train_seasons"]) == Y - 1


def test_all_folds_validate_and_report():
    df = make_pool()
    rep = B.assert_walk_forward_folds(df, "unit")
    assert [f["season"] for f in rep["validated"]] == list(TEST_SEASONS)
    assert rep["unvalidated_empty"] == []


def test_empty_folds_are_reported_not_swallowed():
    df = make_pool()
    df = df[df.season <= 2023]                 # 2024/2025 test folds cannot exist
    rep = B.assert_walk_forward_folds(df, "unit")
    assert [f["season"] for f in rep["validated"]] == [2021, 2022, 2023]
    assert rep["unvalidated_empty"] == [2024, 2025]


def test_no_validatable_fold_raises():
    df = make_pool()
    df = df[df.season <= 2018]
    with pytest.raises(B.FoldLeakError, match="no fold could be validated"):
        B.assert_walk_forward_folds(df, "unit")


# ------------------------------------------------------------------- THE RED PROOF
def _old_guard(vet, Y):
    """The exact expression that used to ship, re-materialised."""
    return bool((vet[vet.season < Y].season < Y).all())


def test_old_guard_is_vacuous_on_injected_leakage():
    """50 target-season rows in the training pool: the OLD guard still says True."""
    Y = 2024
    df = make_pool(n_per_season=60)
    leak = df[df.season == Y].head(50).copy()
    poisoned = pd.concat([df[df.season < Y], leak], ignore_index=True)
    assert (poisoned.season == Y).sum() == 50
    assert _old_guard(poisoned, Y) is True          # <-- the defect, reproduced


def test_red_proof_injected_target_year_row_raises():
    """The SAME poisoned training fold makes the new guard raise."""
    Y = 2024
    df = make_pool(n_per_season=60)
    tr, te = B.build_fold(df, Y)
    leak = te.head(50).copy()
    tr_poisoned = pd.concat([tr, leak])             # index preserved -> also overlaps te
    with pytest.raises(B.FoldLeakError) as e:
        B.assert_walk_forward_fold(tr_poisoned, te, Y, "red", pool=df)
    assert "2024" in str(e.value) and "BOTH folds" in str(e.value)

    # and again with the injected rows given fresh identities, so ONLY the
    # season-set / temporal checks can catch them
    ghost = te.head(50).copy()
    ghost.index = range(900_000, 900_050)
    ghost["player_id"] = [f"GHOST{i}" for i in range(50)]
    with pytest.raises(B.FoldLeakError, match="train seasons"):
        B.assert_walk_forward_fold(pd.concat([tr, ghost]), te, Y, "red", pool=df)


def test_red_proof_single_injected_row_raises():
    Y = 2023
    df = make_pool()
    tr, te = B.build_fold(df, Y)
    one = te.head(1).copy()
    one.index = [999_999]                            # no index overlap, no key overlap
    one["player_id"] = "INTRUDER"
    tr_poisoned = pd.concat([tr, one])
    with pytest.raises(B.FoldLeakError, match="train seasons"):
        B.assert_walk_forward_fold(tr_poisoned, te, Y, "red", pool=df)


def test_red_proof_off_by_one_filter_raises():
    """The classic `<=` construction bug."""
    Y = 2022
    df = make_pool()
    tr = df[df.season <= Y].dropna(subset=["y"])     # WRONG
    te = df[df.season == Y].dropna(subset=["y"])
    with pytest.raises(B.FoldLeakError):
        B.assert_walk_forward_fold(tr, te, Y, "red", pool=df)


def test_strict_max_without_pool_still_raises():
    """Even with pool=None (no season-set expectation) the temporal max is checked."""
    Y = 2022
    df = make_pool()
    tr, te = B.build_fold(df, Y)
    ghost = te.head(3).copy()
    ghost.index = range(700_000, 700_003)            # no index overlap
    ghost["player_id"] = ["G1", "G2", "G3"]          # no key overlap
    tr_poisoned = pd.concat([tr, ghost])
    with pytest.raises(B.FoldLeakError, match="not strictly <"):
        B.assert_walk_forward_fold(tr_poisoned, te, Y, "red", pool=None)


def test_index_overlap_raises():
    Y = 2023
    df = make_pool()
    tr, te = B.build_fold(df, Y)
    te2 = te.copy()
    te2.index = list(tr.index[:len(te2)])            # index collision only
    with pytest.raises(B.FoldLeakError, match="BOTH folds by index"):
        B.assert_walk_forward_fold(tr, te2, Y, "red", pool=df)


def test_player_season_key_overlap_raises():
    """A train row duplicated into the test fold under a fresh index."""
    Y = 2023
    df = make_pool()
    tr, te = B.build_fold(df, Y)
    dup = tr.head(5).copy()
    dup.index = range(600_000, 600_005)              # index no longer overlaps
    te2 = pd.concat([te, dup])
    with pytest.raises(B.FoldLeakError, match="key\\(s\\) in BOTH folds"):
        B.assert_walk_forward_fold(tr, te2, Y, "red", pool=df)


def test_wrong_test_season_raises():
    Y = 2025
    df = make_pool()
    tr, te = B.build_fold(df, Y)
    stray = df[df.season == 2024].head(2).copy()
    stray.index = [800_000, 800_001]                 # no index/key overlap with tr
    stray["player_id"] = ["S1", "S2"]
    te2 = pd.concat([te, stray])
    with pytest.raises(B.FoldLeakError, match="test fold seasons"):
        B.assert_walk_forward_fold(tr, te2, Y, "red", pool=df)


def test_missing_train_season_raises():
    """A silently dropped training season is a fold-construction defect too."""
    Y = 2024
    df = make_pool()
    tr, te = B.build_fold(df, Y)
    tr2 = tr[tr.season != 2020]
    with pytest.raises(B.FoldLeakError, match="missing"):
        B.assert_walk_forward_fold(tr2, te, Y, "red", pool=df)


# ------------------------------------------------- the guard is WIRED INTO the engine
def test_walk_forward_raises_on_a_leaky_fold(monkeypatch):
    """walk_forward() must reject a leaky fold BEFORE any model is fitted."""
    df = make_pool(n_per_season=60)

    def leaky_build_fold(d, Y, y="y"):
        tr = d[d.season <= Y].dropna(subset=[y])     # the off-by-one
        te = d[d.season == Y].dropna(subset=[y])
        return tr, te

    monkeypatch.setattr(B, "build_fold", leaky_build_fold)

    def boom(*a, **k):                                # nothing may be fitted
        raise AssertionError("nested_select reached — the guard did not fire first")
    monkeypatch.setattr(B, "nested_select", boom)

    with pytest.raises(B.FoldLeakError):
        B.walk_forward(df, ["x"], "wired")


def test_run_asserts_walk_forward_block_uses_the_guard():
    src = (HERE / "build_rb_projection.py").read_text(encoding="utf-8")
    body = src.split("def run_asserts(")[1].split("\ndef ")[0]
    assert "assert_walk_forward_folds" in body
    assert "FoldLeakError" in body


# ------------------------------------------------- THE HARNESS RED PROOFS (4 positions)
# The same tautology shipped a second time in the four *_projection_harness.py files:
#     assert (tr.season < Y).all()            with tr = df[df.season < Y]
#     folds_ok = all((v[v.season < Y].season < Y).all() for Y in TEST_SEASONS)
# Both are gone; each harness now builds its folds with B.build_fold and validates the
# ACTUAL train/test objects with B.assert_walk_forward_fold immediately before fitting.
# Each red proof below injects a target-season row AFTER fold construction and asserts
# (a) FoldLeakError is raised and (b) the fitting function was never reached.
HARNESSES = ["rb_projection_harness.py", "wr_projection_harness.py",
             "te_projection_harness.py", "qb_projection_harness.py"]
HARNESS_MODULES = [n[:-3] for n in HARNESSES]
# each harness's own thin-fold floor: the pool must clear it or nothing would be fitted
HARNESS_FLOOR = {"rb_projection_harness": 60, "wr_projection_harness": 60,
                 "te_projection_harness": 40, "qb_projection_harness": 30}


def _import_harness(modname):
    return __import__(modname)


@pytest.mark.parametrize("modname", HARNESS_MODULES)
def test_harness_red_proof_injected_target_season_row_never_reaches_fitting(modname, monkeypatch):
    H = _import_harness(modname)
    assert H.B is B, f"{modname}: not bound to the shared engine"

    df = make_pool(n_per_season=40)
    Y_first = H.TEST_SEASONS[0]
    assert len(df[df.season < Y_first]) >= HARNESS_FLOOR[modname]

    real_build_fold = B.build_fold
    poisoned_seasons = []

    def poisoning_build_fold(d, Y, y="y"):
        """Construct the fold correctly, THEN inject one season-Y row into train with a
        fresh index and a fresh player_id — so only the season-set / temporal checks
        can catch it, not the index or key disjointness checks."""
        tr, te = real_build_fold(d, Y, y=y)
        ghost = te.head(1).copy()
        ghost.index = [990_000 + int(Y)]
        ghost["player_id"] = f"GHOST{Y}"
        poisoned_seasons.append(int(Y))
        return pd.concat([tr, ghost]), te

    fitted = []

    def boom(*a, **k):
        fitted.append(1)
        raise AssertionError(f"{modname}: _fit_pred reached — the guard did not fire first")

    monkeypatch.setattr(B, "build_fold", poisoning_build_fold)
    monkeypatch.setattr(H, "_fit_pred", boom)
    monkeypatch.setattr(H, "nested_select", boom)

    with pytest.raises(B.FoldLeakError) as e:
        H.walk_forward(df, ["x"], "y")

    msg = str(e.value)
    assert str(Y_first) in msg, msg
    assert "train seasons" in msg, msg
    assert fitted == [], f"{modname}: fitting was reached despite the leak"
    assert poisoned_seasons == [Y_first], poisoned_seasons   # raised on the FIRST fold


def test_the_old_harness_guard_would_have_fitted_the_poisoned_fold():
    """Non-vacuity of the four red proofs above: the expressions the harnesses used to
    carry BOTH stay True on the very fold that now raises, so the old code would have
    gone straight on to fit the model."""
    Y = 2021
    df = make_pool(n_per_season=40)
    tr, te = B.build_fold(df, Y)
    ghost = te.head(1).copy()
    ghost.index = [990_000 + Y]
    ghost["player_id"] = f"GHOST{Y}"
    tr_poisoned = pd.concat([tr, ghost])
    assert (tr_poisoned.season == Y).sum() == 1          # the leak is really there

    # form 1 — the per-fold assert inside the old walk_forward
    assert bool((tr_poisoned[tr_poisoned.season < Y].season < Y).all()) is True
    # form 2 — the step-6 `folds_ok` expression
    v = pd.concat([df, ghost])
    assert all(bool((v[v.season < y].season < y).all()) for y in TEST_SEASONS) is True

    # the replacement raises on exactly that frame
    with pytest.raises(B.FoldLeakError, match="train seasons"):
        B.assert_walk_forward_fold(tr_poisoned, te, Y, "old-vs-new", pool=df)


@pytest.mark.parametrize("modname", HARNESS_MODULES)
def test_harness_clean_pool_validates_and_does_reach_fitting(modname, monkeypatch):
    """Control for the red proof: with an unpoisoned pool the guard passes and the
    harness really does get as far as fitting (otherwise the red proof proves nothing)."""
    H = _import_harness(modname)
    df = make_pool(n_per_season=40)
    reached = []

    def fake_fit(tr, te, feats, y_col, params):
        reached.append((int(te.season.iloc[0]), len(tr), len(te)))
        assert int(tr.season.max()) < int(te.season.iloc[0])
        return np.zeros(len(te))

    monkeypatch.setattr(H, "_fit_pred", fake_fit)
    out = H.walk_forward(df, ["x"], "y")
    assert [r[0] for r in reached] == list(H.TEST_SEASONS), reached
    assert len(out) == sum(r[2] for r in reached)


@pytest.mark.parametrize("modname", HARNESS_MODULES)
def test_harness_off_by_one_fold_construction_raises(modname, monkeypatch):
    """The `<=` construction bug, injected at the harness's fold boundary."""
    H = _import_harness(modname)
    df = make_pool(n_per_season=40)

    def leaky(d, Y, y="y"):
        return d[d.season <= Y].dropna(subset=[y]), d[d.season == Y].dropna(subset=[y])

    def boom(*a, **k):
        raise AssertionError("fitting reached")

    monkeypatch.setattr(B, "build_fold", leaky)
    monkeypatch.setattr(H, "_fit_pred", boom)
    monkeypatch.setattr(H, "nested_select", boom)
    with pytest.raises(B.FoldLeakError):
        H.walk_forward(df, ["x"], "y")


# --------------------------------------------- the guard is SHARED, not copy-pasted
TAUTOLOGY = re.compile(r"\[\s*(\w+)\.season\s*<\s*Y\s*\]\.season\s*<\s*Y")
# the second form the harnesses carried: filter by `< Y`, then assert the same predicate
REFILTER_ASSERT = re.compile(r"assert\s*\(\s*\w+\.season\s*<\s*Y\s*\)\.all\(\)")
BUILDERS = ["build_rb_projection.py", "build_wr_projection.py",
            "build_te_projection.py", "build_qb_projection.py"]
SCANNED = BUILDERS + HARNESSES          # all four builders AND all four harnesses


def _executable(name):
    """Source with comment lines removed — prose describing the defect must not make
    the scan fail, and a defect hidden behind a comment must not make it pass."""
    src = (HERE / name).read_text(encoding="utf-8")
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


def test_the_scan_covers_every_builder_and_every_harness():
    assert len(SCANNED) == 8, SCANNED
    for name in SCANNED:
        assert (HERE / name).exists(), name


@pytest.mark.parametrize("name", BUILDERS + HARNESSES)
def test_no_builder_or_harness_still_carries_the_tautology(name):
    code = _executable(name)
    assert not TAUTOLOGY.search(code), f"{name}: vacuous walk-forward guard still present"
    assert not REFILTER_ASSERT.search(code), f"{name}: re-filter-then-re-test assert still present"


@pytest.mark.parametrize("name", HARNESSES)
def test_harness_uses_the_shared_guard_and_defines_none_of_its_own(name):
    src = (HERE / name).read_text(encoding="utf-8")
    code = _executable(name)
    assert "import build_rb_projection as B" in code, f"{name}: not bound to the shared engine"
    assert "B.build_fold(" in code, f"{name}: folds not built by the shared builder"
    assert "B.assert_walk_forward_fold(" in code, f"{name}: per-fold guard not called"
    assert "B.assert_walk_forward_folds(" in code, f"{name}: all-folds guard not called"
    for banned in ("def build_fold(", "def assert_walk_forward_fold(",
                   "def assert_walk_forward_folds(", "class FoldLeakError"):
        assert banned not in src, f"{name}: {banned!r} copy-pasted instead of shared"
    # the per-fold assertion must sit inside walk_forward, before the fit
    body = src.split("def walk_forward(")[1].split("\ndef ")[0]
    assert body.index("B.assert_walk_forward_fold(") < body.index("_fit_pred("), name


def test_wrappers_call_the_shared_guard():
    for name in ["build_wr_projection.py", "build_te_projection.py", "build_qb_projection.py"]:
        src = (HERE / name).read_text(encoding="utf-8")
        assert "B.assert_walk_forward_folds" in src, f"{name}: not using the shared RB-engine guard"
        assert "def assert_walk_forward_fold" not in src, f"{name}: guard copy-pasted, not shared"
        # the walk-forward itself is the engine's, imported not redefined
        assert "walk_forward," in src and "def walk_forward(" not in src, name
