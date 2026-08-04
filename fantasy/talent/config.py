"""OWNER CONFIG + stack constants for the Talent Score build.

WEIGHTS ARE OWNER CONFIG (R13), RATIFIED-2026-07-16 by Joseph (R21) — applied
verbatim from his ratification block. NO CODE PATH MAY ALTER THESE VECTORS.
"""
import os as _os
from pathlib import Path as _Path

_PKG = _Path(__file__).resolve().parent

WEIGHTS = {
    "RB": {"brkTkl_ru": .22, "yac_oe_rec": .28, "explosive": .14,   # RATIFIED-2026-07-16
           "YACcon": .16, "brkTkl_rec": .12, "success": .08},       # RATIFIED-2026-07-16
    "WR": {"cp": .45, "yac_oe": .35, "brkTkl_rec": .20},            # RATIFIED-2026-07-16
    "TE": {"yac_oe": .65, "brkTkl_rec": .35},                       # RATIFIED-2026-07-16
    # R29 (RATIFIED-2026-07-16b), owner's football logic of record: "rushing is
    # important but QBs should not be punished heavily if they make up for it in
    # other facets of the game." Passing .77 / rushing .23.
    "QB": {"cpoe": .33, "bad": .22, "deep": .22,                    # RATIFIED-2026-07-16b
           "qsucc": .16, "q10": .07},                               # RATIFIED-2026-07-16b
}

# Rookie index weights. History: R31 (2026-07-17) set WR fitted weights off the
# one-shot PREREG_rookie_weights_2026-07-17.md; R32/R33 (2026-07-18) supersede:
# - R32: RB is scored on the frozen PBP instrument (rb_pbp_facets_2026.csv +
#   PREREG_pbp_index_2026-07-17.md OUTCOMES: PBP disatt .474 weak-disclosed vs
#   box .298 dead on the clean panel) — the legacy RB box vector is NOT consulted.
# - R33: WR REVERTED to equal thirds. R31's fit did not replicate on the clean
#   panel (+.106 OOF Spearman -> -.009; fitted on the defective step2 panel,
#   ~89/275 = 32% truncated/out-of-scope rows). Equal is the deliberate default.
# NO CODE PATH MAY ALTER THESE VECTORS.
ROOKIE_WEIGHTS = {
    "RB": {"dom_best": .50, "ypc": .50},                         # LEGACY (R32: unused)
    "WR": {"dom_best": 1 / 3, "recshare": 1 / 3, "ypr": 1 / 3},  # R33 equal (reverted)
    "TE": {"dom_best": 1 / 3, "recshare": 1 / 3, "ypr": 1 / 3},  # equal RATIFIED (R31 gate-fail)
}

PF = list(range(2018, 2026))   # lookback 2018+ (ruled)
LAM = 0.20                     # decay — DECLARED, NOT DERIVED; never re-derive

# R22 (RATIFIED-2026-07-16): documented data corrections applied at universe
# construction. Generic mechanism; one entry. Travis Hunter — the stats feed
# miscodes his modal position as CB; the ADP universe lists WR.
POSITION_OVERRIDES = {"00-0040718": "WR"}

# R26 (RATIFIED-2026-07-16): explicit gsis-keyed college-name aliases for the
# rookie JOIN-B — exact candidates verified against espn ids; NO fuzzy matching.
NAME_ALIASES = {
    "00-0040878": "michael washington",   # Mike Washington (Buffalo->Arkansas, espn 4686658)
    "00-0041547": "kevin concepcion",     # K.C. Concepcion (NC State->Texas A&M, espn 4870653)
}

# --- mode switches -----------------------------------------------------------
# reproduction mode: prototype parity (accepted-table regression target)
REPRO = dict(NS=18, SEED=20260714, K_MODE="legacy", QB_MODE="legacy",
             FLOOR=True, DROP_DELTA_BRK=False)
# ruled mode: R1 derived k · R2 NS=60/new seed · R3 no floor · R4/R5/R6 QB ·
# delta dropped from brkTkl facets (record: delta_brk noise, -0.06)
RULED = dict(NS=60, SEED=20260716, K_MODE="derived", QB_MODE="ruled",
             FLOOR=False, DROP_DELTA_BRK=True)

# retired k literals (prototype s2.py l.60-63; mean-sigma_alpha basis; kept ONLY
# as the reproduction-mode compatibility config — R1 forbids them in ruled mode)
LEGACY_K = {
    "RB": {"YACcon": 52, "brkTkl_ru": 560, "success": 143, "explosive": 319,
           "yac_oe_rec": 110, "brkTkl_rec": 173},
    "WR": {"yac_oe": 110, "cp": 516, "brkTkl_rec": 173},
    "TE": {"yac_oe": 58, "brkTkl_rec": 173},
}
LEGACY_QK = {"cpoe": 285, "bad": 399, "qsucc": 12, "q10": 24}   # retired MoM literals

# R10: the pipe ships RB-only at the box-score disattenuated rho (test #2, RHO2.res)
RHO_RB_BOX_DISATT = 0.3852

# display / anchor spec (constrained Bayes)
ANCHOR = dict(lo_pct=5, hi_pct=98, lo_score=52, hi_score=95, clip=(40, 99),
              anchor_min_w=0.30)

# --- checkpoint locations ----------------------------------------------------
# WORK is the BUILD scratch (not repo artifacts). It was hardcoded to
# "C:/tmp/talent_build" -- a machine-local path outside the repo that exists on
# no CI runner, which silently turned every checkpoint-dependent test into a
# SKIP. It is now env-configurable with a repo-relative default.
#   TALENT_WORK=C:/tmp/talent_build   reproduces the historical scratch location.
WORK = _os.environ.get("TALENT_WORK") or str(_PKG / ".work")

# FIXTURE_WORK holds the committed, deterministic checkpoint fixtures the test
# suites read (see tests/fixtures/make_fixtures.py). A build stage never writes
# here. TEST_WORK is what the suites resolve; point TALENT_TEST_WORK at a live
# build dir to run them against a fresh build instead of the fixtures.
FIXTURE_WORK = str(_PKG / "tests" / "fixtures" / "work")
TEST_WORK = _os.environ.get("TALENT_TEST_WORK") or FIXTURE_WORK
