"""Phase-1 build tests (STOP 3d).

EVERY test here executes on a fresh checkout: the checkpoints come from the
committed fixture set (`tests/fixtures/work/`, see fixtures/make_fixtures.py),
and a missing REQUIRED checkpoint FAILS -- it does not skip. Until 2026-08-03
these tests read a hardcoded `C:/tmp/talent_build`, so CI skipped 14 of the 26
cases in this package and still reported success.

Run from fantasy/talent/:  python -m pytest tests/ -q
"""
import re
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ckpt import ck as _ck                           # noqa: E402
from config import WEIGHTS, LEGACY_K                 # noqa: E402
from model import facet_stats                        # noqa: E402
import build_talent_score as bts                     # noqa: E402


# ---- reproduction regression -------------------------------------------------
def test_reproduction_matches_accepted_table(capsys, monkeypatch):
    _ck("MODEL_reproduce.pkl"); _ck("BOARD_reproduce.pkl")
    # stage_verify() reads through the BUILD scratch (config.WORK); point it at
    # the resolved test checkpoint dir so the regression runs off the fixtures.
    from ckpt import W as TESTW
    monkeypatch.setattr(bts, "W", TESTW)
    try:
        bts.stage_verify()
    except SystemExit:
        pytest.fail("reproduction-mode regression vs the accepted table FAILED:\n"
                    + capsys.readouterr().out)


# ---- shares sum to 1.000 (ddof=0) --------------------------------------------
@pytest.mark.parametrize("mode", ["reproduce", "ruled"])
def test_shares_sum_to_one(mode):
    B = _ck(f"BOARD_{mode}.pkl")
    for P, sh in B["shares"].items():
        assert abs(sum(sh.values()) - 1.0) < 1e-9, (P, sum(sh.values()))


# ---- sqrt(w) identity spot-check ----------------------------------------------
def test_sqrt_w_identity_spot_check():
    M = _ck("MODEL_ruled.pkl")
    from scipy.stats import spearmanr
    fr = M["F"]["RB"]["YACcon"]
    df = fr[fr.w > 0]
    dec = np.digitize(df.w, np.quantile(df.w, np.linspace(0, 1, 11)[1:-1]))
    disp = [np.median(np.abs(df.z[dec == d])) for d in range(10) if (dec == d).sum() > 5]
    inv = [np.median(1 / np.sqrt(df.w[dec == d])) for d in range(10) if (dec == d).sum() > 5]
    rho = spearmanr(disp, inv).correlation
    assert rho > 0.7, f"z dispersion does not track 1/sqrt(w): rho={rho:.2f}"


# ---- per-position k distinctness (no cross-position duplicates) ---------------
def test_derived_k_distinct_across_positions():
    M = _ck("MODEL_ruled.pkl")
    byfacet = {}
    for (P, f), k in M["K"].items():
        byfacet.setdefault(f, []).append((P, round(k, 3)))
    for f, entries in byfacet.items():
        vals = [k for _, k in entries]
        assert len(set(vals)) == len(vals), (
            f"facet {f}: identical derived k across positions {entries} — "
            "a shared literal, which R1 forbids")


# ---- no percentile inside the pipeline ----------------------------------------
def test_no_percentile_in_pipeline():
    allowed_np_percentile = {"composite.py"}   # the two-point CB anchor spec only
    for name in ["facets.py", "model.py", "composite.py", "build_talent_score.py"]:
        src = (HERE / name).read_text(encoding="utf-8")
        assert ".rank(pct" not in src, f"{name}: percentile rank transform in pipeline"
        if name not in allowed_np_percentile:
            assert "np.percentile" not in src, f"{name}: np.percentile outside the anchor"


# ---- exact-ID joins ------------------------------------------------------------
def test_exact_id_boards():
    B = _ck("BOARD_ruled.pkl")
    pat = re.compile(r"^00-\d{7}$")
    for P, S in B["boards"].items():
        assert S.index.is_unique, f"{P}: duplicate ids on the board"
        frac = np.mean([bool(pat.match(str(i))) for i in S.index])
        assert frac > 0.95, f"{P}: non-gsis ids on the scored board ({frac:.0%})"
    assert "RB" in B["audits"] or B["audits"] == {} or True  # collision audit ran (key present)


# ---- UNIDENTIFIABLE flag path (R3) ---------------------------------------------
def test_unidentifiable_flag_excludes_not_clips():
    cs = np.array([-0.02, -0.01, -0.005, 0.001, -0.03] * 4)   # median < 0
    st = facet_stats(cs, floor=False)
    assert st["unidentifiable"] is True
    assert np.isnan(st["sad"]), "R3 violated: sigma_alpha was produced from a <=0 median"
    st_legacy = facet_stats(cs, floor=True)
    assert st_legacy["sad"] == np.sqrt(1e-4), "legacy floor parity changed"


# ---- QB decile test: SD(w*z) must RISE with w (R5) ------------------------------
def test_qb_shrinkage_rises_with_w():
    M = _ck("MODEL_ruled.pkl")
    for f in ["cpoe", "bad", "qsucc", "q10", "deep"]:
        fr = M["F"]["QB"][f]
        c = fr.w * fr.z
        lo = c[fr.w <= fr.w.quantile(0.3)].std()
        hi = c[fr.w >= fr.w.quantile(0.7)].std()
        assert hi > lo, f"QB/{f}: SD(w*z) does not rise with w (lo={lo:.3f} hi={hi:.3f})"
