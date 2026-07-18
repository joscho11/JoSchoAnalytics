"""OWNER CONFIG + stack constants for the Talent Score build.

WEIGHTS ARE OWNER CONFIG (R13), RATIFIED-2026-07-16 by Joseph (R21) — applied
verbatim from his ratification block. NO CODE PATH MAY ALTER THESE VECTORS.
"""

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

# R31 (RATIFIED-2026-07-17): rookie box-score index weights, set by the one-shot
# out-of-fold test PREREG_rookie_weights_2026-07-17.md (NOT by hand): WR fitted
# (OOF Spearman IC equal -.021 -> fitted .106, gate +.05/+.10 passed); RB & TE
# equal weights RATIFIED (below gate). NO CODE PATH MAY ALTER THESE VECTORS.
ROOKIE_WEIGHTS = {
    "RB": {"dom_best": .50, "ypc": .50},                        # equal RATIFIED
    "WR": {"dom_best": .80, "recshare": .00, "ypr": .20},       # FITTED (R31)
    "TE": {"dom_best": 1 / 3, "recshare": 1 / 3, "ypr": 1 / 3},  # equal RATIFIED
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

WORK = "C:/tmp/talent_build"   # scratch checkpoints (not repo artifacts)
