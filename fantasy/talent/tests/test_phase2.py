"""Phase-2 hardening tests (R20): determinism, golden regression, schemas,
join lint, dash rule, artifacts, veteran leak, provenance.

All inputs (checkpoints, goldens, shipped artifacts) are REQUIRED: absence is a
hard failure, never a skip -- see tests/ckpt.py for the 2026-08-03 rationale.
"""
import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ckpt import ck as _ck, art as _art, golden as _golden     # noqa: E402
from config import LEGACY_K, RHO_RB_BOX_DISATT                 # noqa: E402
from schemas import validate, SchemaError, is_nfl              # noqa: E402

PIPE_FILES = ["facets.py", "model.py", "composite.py", "build_talent_score.py",
              "build_rookie_score.py", "schemas.py"]


# ---- (a) determinism -----------------------------------------------------------
def test_model_determinism_two_builds_identical():
    M1, M2 = _ck("MODEL_ruled.pkl"), _ck("MODEL_ruled2.pkl")
    for P in M1["F"]:
        for f in M1["F"][P]:
            pd.testing.assert_frame_equal(M1["F"][P][f], M2["F"][P][f])
    assert {k: round(v, 12) for k, v in M1["K"].items()} == \
           {k: round(v, 12) for k, v in M2["K"].items()}


def test_board_and_artifact_determinism():
    B1, B2 = _ck("BOARD_ruled.pkl"), _ck("BOARD_ruled2.pkl")
    for P in B1["boards"]:
        pd.testing.assert_frame_equal(B1["boards"][P], B2["boards"][P])
    _art("talent_score_2026.csv")   # REQUIRED: fails loudly if the CSV is absent
    h = hashlib.md5((HERE / "talent_score_2026.csv").read_bytes()
                    .replace(b"\r\n", b"\n")).hexdigest()   # LF-normalize (see rookie test)
    g = _golden("golden_weighted.json")
    assert h == g["artifact_md5"]["talent_score_2026.csv"]


# ---- (b) golden regression (split: facets = weight-independent) ----------------
def test_golden_facets_weight_independent():
    g = _golden("golden_facets.json")
    M = _ck("MODEL_ruled.pkl")
    for key, row in g["facets"].items():
        P, f = key.split("/")
        st = M["QU"][(P, f)]
        for col in ["sad", "sam", "cs_std", "cv", "le0"]:
            assert abs(st[col] - row[col]) < 1e-12, (key, col, st[col], row[col])
        assert abs(M["K"][(P, f)] - row["k"]) < 1e-9, key
        assert len(M["F"][P][f]) == row["n_fit"], (key, "fit universe moved")


def test_golden_weighted():
    g = _golden("golden_weighted.json")
    B = _ck("BOARD_ruled.pkl")
    for P, order in g["rank_order"].items():
        assert list(B["boards"][P].index) == order, f"{P} rank order moved"
    for P, sh in g["eff_shares"].items():
        for f, v in sh.items():
            assert abs(B["shares"][P][f] - v) < 1e-12, (P, f)


def test_golden_rookie_artifact():
    g = _golden("golden_weighted.json")
    _art("rookie_score_2026.csv")   # REQUIRED
    p = HERE / "rookie_score_2026.csv"
    # LF-normalize before hashing: the golden is a blob-basis (LF) md5, but
    # `* text=auto` + core.autocrlf=true smudges this CSV to CRLF on a fresh
    # Windows checkout — so a raw worktree hash is checkout-dependent and would
    # fail on a fresh clone. Normalizing makes the check checkout-independent.
    assert hashlib.md5(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == \
        g["artifact_md5"]["rookie_score_2026.csv"]


# ---- (c) schema validation fails loud ------------------------------------------
def test_schema_fails_loud():
    df = pd.DataFrame({"pid": ["a", None], "y": [1.0, 2.0]})
    with pytest.raises(SchemaError, match="NaN in key column"):
        validate(df, "t", no_nan=["pid"])
    with pytest.raises(SchemaError, match="missing columns"):
        validate(df, "t", required=["w"])


# ---- (d) join lint: no surname substring, crosswalk identity-only --------------
def test_no_name_substring_matching_in_package():
    pat = re.compile(r"\.str\.contains\(")
    for name in PIPE_FILES + ["archive_rho.py"]:
        src = (HERE / name).read_text(encoding="utf-8")
        assert not pat.search(src), f"{name}: .str.contains found — substring joins forbidden"


def test_no_name_in_crosswalk():
    src = (HERE / "facets.py").read_text(encoding="utf-8")
    block = src.split("p2g = ")[1].split("\n")[0]
    assert "name" not in block.lower(), "crosswalk must map ids only (IDENTITY ONLY)"


# ---- (e) no percentile in pipeline (Phase 2 files included) --------------------
def test_no_percentile_in_pipeline_phase2():
    for name in PIPE_FILES:
        src = (HERE / name).read_text(encoding="utf-8")
        assert ".rank(pct" not in src, f"{name}: percentile transform in pipeline"
        if name not in ("composite.py", "build_rookie_score.py"):
            assert "np.percentile" not in src, f"{name}: np.percentile outside anchors"


# ---- R22 position override -------------------------------------------------------
def test_position_override_travis_hunter():
    from config import POSITION_OVERRIDES
    assert POSITION_OVERRIDES == {"00-0040718": "WR"}, "R22: single documented entry"
    fac = _ck("FACETS.pkl")
    in_wr = any("00-0040718" in set(df.pid) for _, df in fac["defs"]["WR"])
    # The "R22 rebuild pending" skip was removed 2026-08-03: the checkpoints are
    # now pinned fixtures built AFTER the override, so a miss is a real failure.
    assert in_wr, "R22: 00-0040718 absent from every WR facet fit frame"
    B = _ck("BOARD_ruled.pkl")
    assert "00-0040718" in B["boards"]["WR"].index, "R22: not on the WR scored board"
    for P in ["RB", "TE", "QB"]:
        assert "00-0040718" not in B["boards"][P].index


# ---- dash rule (R12) edge cases -------------------------------------------------
def test_dash_rule_edge_cases():
    nfl_ids = {"00-0000001", "00-0000003"}
    assert is_nfl("00-0000001", nfl_ids) is True      # 3-career-snap player -> Talent
    assert is_nfl("00-0000002", nfl_ids) is False     # never-debuted PS -> Rookie
    assert is_nfl("00-0000003", nfl_ids) is True      # Week-17 UDFA debut -> Talent


def test_dash_rule_disjoint_artifacts():
    t, r = _art("talent_score_2026.csv"), _art("rookie_score_2026.csv")
    both = set(t.gsis_id) & set(r.gsis_id)
    assert not both, f"players with BOTH cells populated: {both}"


# ---- artifact invariants ---------------------------------------------------------
def test_talent_artifact_invariants():
    t = _art("talent_score_2026.csv")
    assert not t.duplicated(["gsis_id", "position"]).any()
    ship = ["gsis_id", "display_name", "position", "score", "ci_lo", "ci_hi",
            "w", "rank_pos", "college_share"]
    assert not t[ship].isna().any().any(), "NaN in shipped columns"
    assert t.score.between(40, 99).all()
    for P, grp in t.groupby("position"):
        assert sorted(grp.rank_pos) == list(range(1, len(grp) + 1))
    fac = _ck("FACETS.pkl")
    assert t.gsis_id.map(lambda g: is_nfl(g, fac["nfl_ids"])).all(), \
        "non-NFL player on the Talent artifact"


def test_cross_artifact_reproduces_from_pickles():
    t = _art("talent_score_2026.csv"); B = _ck("BOARD_ruled.pkl")
    for P, grp in t.groupby("position"):
        S = B["boards"][P]
        m = grp.set_index("gsis_id")
        assert np.allclose(m.w, S.loc[m.index, "w"].round(4), atol=1e-9)
        # CSV loading gives player IDs an object index; the scratch checkpoint preserves
        # pandas StringDtype. The selected rows are already in m's player order, so compare
        # their rank values directly instead of requiring identical index dtypes.
        assert np.array_equal(m.rank_pos.to_numpy(), S.loc[m.index, "rank_pos"].to_numpy())
        if P == "RB":
            has = m.college_share > 0
            expect = ((1 - S.loc[m.index, "w"]) * RHO_RB_BOX_DISATT).round(4)
            assert np.allclose(m.college_share[has], expect[has], atol=1e-9), \
                "college_share != (1-w)*rho at RB rows"


def test_veteran_leak_dissolved():
    t = _art("talent_score_2026.csv").set_index("gsis_id")
    bijan = t.loc["00-0038542"]
    assert abs(bijan.college_share - 0.10) < 0.03, \
        f"RED ALERT: Bijan college share {bijan.college_share:.2f} vs dissolved ~0.10"
    for g in ["00-0036900", "00-0036322", "00-0037744"]:   # Chase, Jefferson, McBride
        assert t.loc[g].college_share == 0.0, \
            "WR/TE pipe is DEAD (R10) — college share must be exactly 0"


def test_provenance_sidecars():
    import json
    for n in ["talent_score_2026", "rookie_score_2026"]:
        _art(f"{n}.csv")   # REQUIRED
        p = HERE / f"{n}.provenance.json"
        assert p.exists(), f"REQUIRED provenance sidecar missing: {p}"
        s = json.loads(p.read_text())
        for k in ["built_utc", "git_head", "config_md5", "NS", "seed", "code_version"]:
            assert k in s, (n, k)
        assert s["NS"] == 60 and s["seed"] == 20260716


def test_refresh_board_adp_excludes_new_artifacts():
    src = (HERE.parent / "seasonal_projections" / "refresh_board_adp.py").read_text(
        encoding="utf-8", errors="ignore")
    assert "talent_score_2026" not in src and "rookie_score_2026" not in src
