"""Proof for the NFL QB Talent Score (SPEC R34, shipped 2026-07-27).

The load-bearing checks are the two that were actually got wrong during development:
  1. k is per-facet, pool-derived, in each facet's OWN denominator — never one constant off the
     scored player's passing sample (that units mismatch crushed grades_run and produced a
     false finding).
  2. the college blend is gated on CAREER NFL seasons, not window volume — otherwise an injured
     veteran gets scored partly on decade-old college tape.

Hermetic (APP_OFFLINE=1); reads shipped artifacts only, writes nothing.
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd

os.environ["APP_OFFLINE"] = "1"

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "fantasy" / "talent"))

ARTIFACT = _HERE / "fantasy" / "talent" / "nfl_qb_score_2026.csv"
PROV = _HERE / "fantasy" / "talent" / "nfl_qb_score_2026.provenance.json"
FACETS = ["grades_pass", "CPOE", "btt_rate", "twp_rate", "pressure_grades_pass",
          "accuracy_pct", "EPA_dropback", "deep_CPOE", "grades_run"]


def test_artifact_and_ratified_constants():
    assert ARTIFACT.exists(), "nfl_qb_score_2026.csv missing — run build_nfl_qb_score.py"
    df = pd.read_csv(ARTIFACT)
    assert len(df) >= 40, f"qualified-starter pool suspiciously small: {len(df)}"
    assert df["score"].between(50, 99).all(), "score outside the ratified [50, 99] clip"
    assert not df["gsis_id"].duplicated().any()

    import build_nfl_qb_score as build
    assert abs(sum(build.WEIGHTS.values()) - 1.0) < 1e-9
    assert build.GAMMA == 0.55 and build.T == 2025
    assert build.POOL_FLOOR == 300, "pool = qualified starters, 300+ dropbacks in window"
    assert build.CAREER_MAX == 3
    assert build.ANCHOR["clip"] == (50, 99), "50 is the floor for any scored player"
    # twp_rate is sign-flipped ONCE, in Stage 1, and carried at a POSITIVE weight
    assert build.SIGN["twp_rate"] == -1 and build.WEIGHTS["twp_rate"] > 0


def test_k_is_per_facet_pool_derived_and_in_own_units():
    """The bug this guards: one k for all nine facets, taken from the scored player's passing
    sample. That judges ~50 designed runs against a ~600-dropback constant."""
    prov = json.loads(PROV.read_text(encoding="utf-8"))
    k = prov["mom_k"]
    assert len(set(k.values())) == len(FACETS), "k must differ across facets — a shared constant"
    # each facet's k lives in its own denominator: the rushing/deep facets are counted in far
    # smaller units than dropbacks, so their k must be far smaller.
    assert k["grades_run"] < k["grades_pass"] / 5, \
        "grades_run k must be in designed-run units, not dropbacks"
    assert k["deep_CPOE"] < k["grades_pass"], "deep_CPOE k must be in deep-attempt units"

    # and the resulting reliability must NOT punish grades_run hardest
    df = pd.read_csv(ARTIFACT)
    r = {f: (df[f"neff_{f}"] / (df[f"neff_{f}"] + k[f])).median() for f in FACETS}
    assert r["grades_run"] > min(r.values()), \
        "grades_run is shrinking hardest — the units mismatch is back"

    # k_blend is a DIFFERENT object and must not be merged into the facet vector
    assert "k_blend" in prov and prov["k_blend"] not in k.values()


def test_college_blend_is_gated_on_career_seasons_not_window_volume():
    df = pd.read_csv(ARTIFACT)
    veterans = df[df["nfl_seasons"] > 3]
    assert (veterans["lambda"] == 1.0).all(), \
        "a veteran must take ZERO college regardless of how thin his window is"
    assert not veterans["blend_applies"].any()

    # the case that motivated the rule: a long-career QB with a thin window
    thin = veterans.nsmallest(3, "N_eff")
    assert (thin["lambda"] == 1.0).all(), f"thin-window veterans blended: {list(thin.player)}"

    blended = df[df["blend_applies"]]
    if len(blended):
        assert (blended["nfl_seasons"] <= 3).all()
        assert (blended["lambda"] < 1.0).all()


def test_board_prefers_r34_for_qbs_and_leaves_sub_pool_qbs_blank():
    import draft_board_2026 as board

    df = board._load_board_2026().reset_index()
    qb = df[df["position"] == "QB"]
    art = pd.read_csv(ARTIFACT).dropna(subset=["gsis_id"]).set_index("gsis_id")["score"]

    scored = qb[qb["nfl_talent"].notna()]
    assert len(scored) >= 20, "most board QBs should carry an R34 score"
    for row in scored.itertuples():
        assert abs(float(row.nfl_talent) - float(art.get(row.player_id))) < 1e-6, \
            f"{row.player} does not match the R34 artifact"

    # QBs below the qualified pool are BLANK, never silently backfilled from R29
    r29 = pd.read_csv(_HERE / "fantasy" / "talent" / "talent_score_2026.csv")
    r29_qb = r29[r29["position"] == "QB"].set_index("gsis_id")["score"]
    for row in qb[qb["nfl_talent"].isna()].itertuples():
        assert row.player_id not in art.index
        # they may well have an R29 value; the board must NOT show it
        _ = r29_qb.get(row.player_id)

    # MIGRATION COMPLETE 2026-07-27: every position now reads a dedicated build (QB R34,
    # RB R37, WR R39, TE R41), so talent_score_2026.csv feeds NO board column. It stays on
    # disk, unregenerated, for the closed campaign — asserted byte-identical below.
    r29_all = r29.set_index("gsis_id")["score"]
    te = df[df["position"].eq("TE") & df["nfl_talent"].notna()]
    r41 = pd.read_csv(_HERE / "fantasy" / "talent" / "nfl_te_score_2026.csv")
    r41 = r41.dropna(subset=["gsis_id"]).set_index("gsis_id")["score"]
    assert len(te) >= 20
    for row in te.itertuples():
        assert abs(float(row.nfl_talent) - float(r41.get(row.player_id))) < 1e-6,             f"{row.player} TE row is not reading R41"
    paths_all = [p for p, _m, _s in board._board_source_fingerprint()]
    assert str(board.NFL_TE_CSV) in paths_all

    paths = [p for p, _m, _s in board._board_source_fingerprint()]
    assert str(board.NFL_QB_CSV) in paths


def test_nfl_rb_score_ships_on_a_qualified_pool_and_owns_rb_rows():
    """R37 replaces the R29 value for RB rows only. An RB below the 100-carry volume floor is
    left BLANK — never mixed across two scales — and no other position is touched."""
    import draft_board_2026 as board

    art_path = _HERE / "fantasy" / "talent" / "nfl_rb_score_2026.csv"
    assert art_path.exists(), "nfl_rb_score_2026.csv missing — run build_nfl_rb_score.py"
    art = pd.read_csv(art_path)
    assert art["score"].between(50, 99).all(), "score outside the ratified [50, 99] clip"
    assert not art["gsis_id"].dropna().duplicated().any()
    # the career gate: a veteran must never take a college share
    vets = art[art["nfl_seasons"] > 3]
    assert (vets["lambda"] == 1.0).all(), "a veteran RB was blended with college tape"

    import build_nfl_rb_score as build
    assert build.POOL_CARRIES == 100 and build.GAMMA == 0.55
    assert abs(sum(build.RUSH.values()) - 0.60) < 1e-9, "ratified 60 rush"
    assert abs(sum(build.RECV.values()) - 0.40) < 1e-9, "ratified 40 receive"
    assert build.SIGN["drop_rate"] == -1 and build.W["drop_rate"] > 0

    df = board._load_board_2026().reset_index()
    by_id = art.dropna(subset=["gsis_id"]).set_index("gsis_id")["score"]
    rb = df[df["position"] == "RB"]
    scored = rb[rb["nfl_talent"].notna()]
    assert len(scored) >= 40
    for row in scored.itertuples():
        assert abs(float(row.nfl_talent) - float(by_id.get(row.player_id))) < 1e-6
    for row in rb[rb["nfl_talent"].isna()].itertuples():
        assert row.player_id not in by_id.index, "a scored RB was left blank"

    paths = [p for p, _m, _s in board._board_source_fingerprint()]
    assert str(board.NFL_RB_CSV) in paths


def test_nfl_wr_score_owns_wr_rows_and_blend_is_near_zero():
    """R39 owns WR rows. Also guards the EB behaviour: College_WR is a dead instrument, so its
    median contribution among blended players must stay small on its own."""
    import draft_board_2026 as board

    art_path = _HERE / "fantasy" / "talent" / "nfl_wr_score_2026.csv"
    assert art_path.exists(), "nfl_wr_score_2026.csv missing — run build_nfl_wr_score.py"
    art = pd.read_csv(art_path)
    assert art["score"].between(50, 99).all()
    vets = art[art["nfl_seasons"] > 3]
    assert (vets["lambda"] == 1.0).all(), "a veteran WR was blended with college tape"

    prov = json.loads((_HERE / "fantasy" / "talent"
                       / "nfl_wr_score_2026.provenance.json").read_text(encoding="utf-8"))
    assert prov["median_college_weight_among_blended"] < 0.15,         "a DEAD college instrument is carrying real weight — k_lambda estimation problem"
    # the archetype block cannot be rescued by weight — record that it under-delivers
    assert prov["archetype_block"]["effective"] < prov["archetype_block"]["nominal"]

    df = board._load_board_2026().reset_index()
    by_id = art.dropna(subset=["gsis_id"]).set_index("gsis_id")["score"]
    wr = df[df["position"] == "WR"]
    scored = wr[wr["nfl_talent"].notna()]
    assert len(scored) >= 60
    for row in scored.itertuples():
        assert abs(float(row.nfl_talent) - float(by_id.get(row.player_id))) < 1e-6
    paths = [p for p, _m, _s in board._board_source_fingerprint()]
    assert str(board.NFL_WR_CSV) in paths


_BUILDS = {
    "build_nfl_qb_score": ("R34", "nfl_qb_score_2026"),
    "build_college_qb_score": ("R35", "college_qb_score_2026"),
    "build_college_rb_score": ("R36", "college_rb_score_2026"),
    "build_nfl_rb_score": ("R37", "nfl_rb_score_2026"),
    "build_college_wr_score": ("R38", "college_wr_score_2026"),
    "build_nfl_wr_score": ("R39", "nfl_wr_score_2026"),
    "build_college_te_score": ("R40", "college_te_score_2026"),
    "build_nfl_te_score": ("R41", "nfl_te_score_2026"),
}


def test_importing_a_build_never_runs_it():
    """Six of the eight builds once had no __main__ guard, so `import build_nfl_rb_score` (which
    this very file does) executed the whole build and REWROTE the shipped artifact + provenance
    on every test run. Byte-identical against a warm nflreadpy cache, and therefore invisible —
    until the upstream data moved. Every build must now expose build() and do nothing on import."""
    import importlib

    talent = _HERE / "fantasy" / "talent"
    before = {name: (talent / f"{stem}.csv").stat().st_mtime_ns
              for name, (_spec, stem) in _BUILDS.items()}
    prov_before = {name: (talent / f"{stem}.provenance.json").stat().st_mtime_ns
                   for name, (_spec, stem) in _BUILDS.items()}

    for name in _BUILDS:
        module = importlib.import_module(name)
        assert callable(getattr(module, "build", None)), \
            f"{name} must expose build() — module-level work runs on import"

    for name, (_spec, stem) in _BUILDS.items():
        assert (talent / f"{stem}.csv").stat().st_mtime_ns == before[name], \
            f"importing {name} rewrote {stem}.csv"
        assert (talent / f"{stem}.provenance.json").stat().st_mtime_ns == prov_before[name], \
            f"importing {name} rewrote {stem}.provenance.json"


def test_every_provenance_records_its_own_spec():
    """Both TE builds were adapted from their WR sibling and shipped carrying the WR spec number
    (college TE said R38, NFL TE said R39), so provenance could not identify which spec governed
    a TE score. Each artifact must name its own spec, and no two may collide."""
    talent = _HERE / "fantasy" / "talent"
    seen = {}
    for name, (spec, stem) in _BUILDS.items():
        prov = json.loads((talent / f"{stem}.provenance.json").read_text(encoding="utf-8"))
        assert prov["spec"].startswith(spec + " "), \
            f"{stem}.provenance.json says {prov['spec']!r}, expected {spec}"
        assert prov["spec"] not in seen, \
            f"{stem} shares a spec number with {seen.get(prov['spec'])}"
        seen[prov["spec"]] = stem
        # the recorded md5 must be the artifact actually on disk
        import hashlib
        assert prov["md5"] == hashlib.md5((talent / f"{stem}.csv").read_bytes()).hexdigest(), \
            f"{stem}.provenance.json md5 does not match the shipped CSV"
    assert len(seen) == 8


def test_block_weights_in_provenance_are_computed_not_transcribed():
    """The NFL TE provenance hardcoded its WR sibling's block weights (0.400 / 0.175) against
    TE's real 0.430 / 0.145, while the file's own docstring said 43%. Both must agree with W."""
    import importlib

    talent = _HERE / "fantasy" / "talent"
    for name, route_facets, archetype_facets in (
        ("build_nfl_wr_score", ("yprr", "grades_pass_route"),
         ("contested_catch_rate", "deep_explosive")),
        ("build_nfl_te_score", ("yprr", "grades_pass_route"),
         ("contested_catch_rate", "deep_explosive")),
    ):
        module = importlib.import_module(name)
        prov = json.loads(
            (talent / f"{_BUILDS[name][1]}.provenance.json").read_text(encoding="utf-8"))
        assert abs(prov["route_block"]["nominal"]
                   - sum(module.W[f] for f in route_facets)) < 1e-9, \
            f"{name}: route_block nominal does not match W"
        assert abs(prov["archetype_block"]["nominal"]
                   - sum(module.W[f] for f in archetype_facets)) < 1e-9, \
            f"{name}: archetype_block nominal does not match W"


def test_shipped_talent_score_artifact_was_not_regenerated():
    """Joseph's call 2026-07-27: leave the existing artifacts alone. R34 is additive."""
    import hashlib
    md5 = hashlib.md5((_HERE / "fantasy" / "talent" / "talent_score_2026.csv").read_bytes()).hexdigest()
    assert md5 == "d7c1a57547be4ab8060c053de02aaead", "talent_score_2026.csv must not move"


if __name__ == "__main__":
    test_artifact_and_ratified_constants()
    test_k_is_per_facet_pool_derived_and_in_own_units()
    test_college_blend_is_gated_on_career_seasons_not_window_volume()
    test_board_prefers_r34_for_qbs_and_leaves_sub_pool_qbs_blank()
    test_nfl_rb_score_ships_on_a_qualified_pool_and_owns_rb_rows()
    test_nfl_wr_score_owns_wr_rows_and_blend_is_near_zero()
    test_importing_a_build_never_runs_it()
    test_every_provenance_records_its_own_spec()
    test_block_weights_in_provenance_are_computed_not_transcribed()
    test_shipped_talent_score_artifact_was_not_regenerated()
    print("OK  NFL QB talent score: constants, per-facet k in own units, career-gated blend, "
          "board prefers R34 for QBs, shipped artifacts untouched")
