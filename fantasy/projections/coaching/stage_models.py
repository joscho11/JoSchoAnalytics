"""PHASE 1E/1F (prereg v3.8 PREFIT) — Stage 1 / Stage 2 HELPER FUNCTIONS.

**STATUS: HELPERS IMPLEMENTED AND SYNTHETICALLY TESTED. THE PIPELINE IS NOT COMPLETE.**

An earlier report described 1E/1F as "implemented", which overstated this module. What exists here
is: target centering, preprocessing, fold construction, a ONE-dimensional alpha selector,
`block_ridge`, and partial Stage 2 matrix construction.

What does NOT exist yet, and is required before any real fit:
  - Stage 1 inner-CV fitting loop and final target-season fits
  - Stage 1 residual/prediction persistence and feature-schema export
  - Stage 2 inner-CV scoring
  - JOINT two-dimensional (alpha_caller, alpha_hc_context) selection -- `select_alpha` is 1-D
  - final Stage 2 fits, tuning/fold diagnostics, effect persistence
  - an executable build entry point

**NOT EXECUTED ON REAL OUTCOMES.** Synthetic tests only. The preliminary `arm3_residuals.csv` /
`arm3_effects.csv` remain on disk, untouched and UNINTERPRETABLE.

=====================================================================================================
STAGE 1 — estimand and time treatment
=====================================================================================================
The earlier design claimed a "season fixed effect" for the target season. That is not identifiable:
season S's coefficient cannot be estimated from seasons < S. It is replaced by an explicitly
prospective construction.

For each historical season S:

    relative_epa_play(team, S) = epa_play(team, S) - mean_over_teams(epa_play(., S))

`relative_epa_play` is the Stage 1 TARGET. The same-season league mean is used ONLY as historical
outcome normalization -- it is never a predictor, and it is never consumed by any model that runs
before season S is complete. Centering removes league-wide era shifts (rule changes, scoring
inflation) without inventing a coefficient for an unseen target season.

    team_offense_residual = observed relative_epa_play - predicted relative_epa_play

**Naming discipline:** `predicted_relative_epa_play` is a prediction of a CENTERED quantity. It is
NOT an absolute preseason EPA forecast and must never be reported as one.

=====================================================================================================
STAGE 2 — identity design
=====================================================================================================
Residuals from seasons < Y only. Design built from historical game-share exposures:

    caller block                 role = caller
    non-calling HC context block role = noncalling_hc_context

Exposure fractions stay in [0, 1]. A self-calling HC contributes ONLY to the portable caller block.
A distinct known caller permits the HC-context block. **Unknown games contribute zero to both.**

Unpenalized intercept, and SEPARATE ridge penalties `alpha_caller` / `alpha_hc_context`. A single
shared penalty imposes the same variance prior on two blocks with very different support -- the
caller block is dense and the context block is sparse (3,549 person-games vs a caller block an order
of magnitude larger), so one alpha silently over-shrinks one of them.

FORBIDDEN in the Stage 2 identity matrix: `hc_resume`, `unknown_caller_hc_games`, any observed game
count, `observed_reliability`, censoring fields, calendar proxies. Enforced by
`build_reliability.assert_design_matrix_is_clean`.
"""
import numpy as np
import pandas as pd

import build_reliability as BR

# ---------------------------------------------------------------- frozen constants
ALPHA_GRID = np.logspace(-4, 8, 25)          # half-decade spacing, 1e-4 .. 1e8
GRID_STEP_DECADES = 0.5
EXTEND_DECADES = 4.0                         # per extension
MAX_EXTENSIONS_PER_DIRECTION = 2

# Frozen per-stage temporal-CV minimums (prereg v3.8). Set BEFORE fitting; never relaxed after
# inspecting results. Stage 2 is deliberately looser because it consumes Stage 1 residuals, which
# only begin in 2014 -- entering-2018 therefore validates on 2016 and 2017.
STAGE1_MIN_TRAIN_SEASONS = 5
STAGE1_MIN_VALIDATION_SEASONS = 3
STAGE2_MIN_TRAIN_SEASONS = 2
STAGE2_MIN_VALIDATION_SEASONS = 2

MISSING_QB = "__MISSING_QB__"
UNSEEN_QB = "__UNSEEN_QB__"

STAGE1_NUMERIC = [
    "prior_epa_play", "prior_success_rate", "prior_drive_scoring_points_per_drive_proxy",
    "prior_plays",
    "prior_pass_rate", "prior_ol_sack_rate", "prior_qb_epa_play", "prior_qb_cpoe",
    "ret_qb_attempt_share", "ret_rb_carry_share", "ret_wrte_target_share",
    "vacated_rush_share", "vacated_target_share", "ret_skill_fantasy_share",
]
STAGE1_BINARY = ["qb_returns", "relocated"]          # natural 0/1, never standardized
STAGE1_CATEGORICAL = ["prior_qb_id"]
STAGE1_PREDICTORS = STAGE1_NUMERIC + STAGE1_BINARY + STAGE1_CATEGORICAL


# ================================================================ Stage 1 target
def relative_epa_play(df, season_col="season", value_col="epa_play"):
    """Same-season league centering. Returns a copy with `relative_epa_play` added.

    Historical outcome normalization ONLY. The league mean of season S is a function of season S's
    completed results and must never reach a predictor used before S.
    """
    out = df.copy()
    out["league_mean_epa_play"] = out.groupby(season_col)[value_col].transform("mean")
    out["relative_epa_play"] = out[value_col] - out["league_mean_epa_play"]
    return out


# ================================================================ preprocessing
class Stage1Preprocessor:
    """Fit ONLY on inner-training rows. Medians, scaling and QB vocabulary are all learned there.

    An unseen target-season QB maps to UNSEEN_QB and therefore receives the zero league-prior
    identity contribution -- never a coefficient learned from target-season data.
    """

    def __init__(self):
        self.medians_, self.mean_, self.std_, self.qb_vocab_, self.columns_ = (
            None, None, None, None, None)
        self.all_missing_in_train_ = []

    def fit(self, X):
        num = X[STAGE1_NUMERIC].astype(float)
        med = num.median()
        # A predictor can be ENTIRELY absent from an inner-training fold -- `prior_qb_cpoe` does
        # not exist before ~2006, and Stage 1 folds reach back to 1999. Its median is then NaN,
        # which silently propagated NaN through the whole design and made every alpha score NaN.
        # Such a column is imputed to 0 and, with mean 0 / std 1, standardises to a constant 0:
        # the honest "no information available in this fold" contribution. Recorded so the schema
        # shows which folds lacked which predictor.
        self.all_missing_in_train_ = sorted(med.index[med.isna()])
        self.medians_ = med.fillna(0.0)
        filled = num.fillna(self.medians_)
        self.mean_ = filled.mean().fillna(0.0)
        std = filled.std(ddof=0).fillna(0.0)
        self.std_ = std.replace(0.0, 1.0)
        qb = X[STAGE1_CATEGORICAL[0]].fillna(MISSING_QB).astype(str)
        self.qb_vocab_ = sorted(set(qb) | {MISSING_QB, UNSEEN_QB})
        self.columns_ = (list(STAGE1_NUMERIC) + list(STAGE1_BINARY)
                         + [f"qb__{v}" for v in self.qb_vocab_])
        return self

    def transform(self, X):
        num = X[STAGE1_NUMERIC].astype(float).fillna(self.medians_)
        z = ((num - self.mean_) / self.std_).fillna(0.0)
        binary = X[STAGE1_BINARY].astype(float).fillna(0.0)     # natural 0/1, NOT standardized
        qb = X[STAGE1_CATEGORICAL[0]].fillna(MISSING_QB).astype(str)
        qb = qb.where(qb.isin(self.qb_vocab_), UNSEEN_QB)       # unseen -> explicit level
        dummies = pd.DataFrame(
            {f"qb__{v}": (qb == v).astype(float).values for v in self.qb_vocab_}, index=X.index)
        out = pd.concat([z, binary, dummies], axis=1)
        return out[self.columns_]


# ================================================================ temporal CV
def expanding_folds(seasons, target_season, min_train_seasons=3, min_validation_seasons=2):
    """Expanding forward-chaining folds, FROZEN before fitting.

        inner training seasons < validation season < outer target season

    No shuffled folds, no generalized LOO, and no fold that trains on seasons after its validation
    season. Returns [] when the frozen minimums are not met, rather than silently shrinking them.
    """
    hist = sorted(s for s in set(seasons) if s < target_season)
    folds = [(tuple(hist[:i]), hist[i]) for i in range(len(hist)) if i >= min_train_seasons]
    if len(folds) < min_validation_seasons:
        return []
    return folds


def season_averaged_mse(errors_by_season):
    """Average SEASON-level MSEs so a season with more rows does not dominate tuning."""
    per = [float(np.mean(np.asarray(e, dtype=float) ** 2)) for e in errors_by_season if len(e)]
    return float(np.mean(per)) if per else np.inf


# ================================================================ frozen alpha protocol
def _grid(lo_exp, hi_exp):
    n = int(round((hi_exp - lo_exp) / GRID_STEP_DECADES)) + 1
    return np.logspace(lo_exp, hi_exp, n)


def select_alpha(score_fn, lo_exp=-4.0, hi_exp=8.0):
    """Frozen boundary protocol.

    Start at logspace(-4, 8, 25). If the optimum lands on a boundary, extend THAT boundary by four
    decades at the same half-decade spacing, at most twice per direction. Exact score ties resolve
    toward the LARGER alpha (more shrinkage, the conservative choice). If the final upper boundary
    is still preferred, that is recorded as effective complete pooling -- an interior solution is
    never forced.
    """
    ext_lo = ext_hi = 0
    history = []
    while True:
        grid = _grid(lo_exp, hi_exp)
        scores = np.array([float(score_fn(a)) for a in grid])
        assert np.isfinite(scores).any(), (
            "every alpha scored non-finite -- the design or target contains NaN. Fix the data "
            "contract; do not let a silent NaN choose the penalty.")
        scores = np.where(np.isfinite(scores), scores, np.inf)
        history.append(dict(lo_exp=lo_exp, hi_exp=hi_exp,
                            alphas=grid.tolist(), scores=scores.tolist()))
        best = float(np.min(scores))
        # tie -> LARGEST alpha achieving the best score
        idx = int(np.max(np.where(scores == best)[0]))
        at_lo, at_hi = idx == 0, idx == len(grid) - 1
        if at_lo and ext_lo < MAX_EXTENSIONS_PER_DIRECTION:
            lo_exp -= EXTEND_DECADES; ext_lo += 1; continue
        if at_hi and ext_hi < MAX_EXTENSIONS_PER_DIRECTION:
            hi_exp += EXTEND_DECADES; ext_hi += 1; continue
        return dict(alpha=float(grid[idx]), score=best,
                    at_lower_boundary=bool(at_lo), at_upper_boundary=bool(at_hi),
                    boundary_unresolved=bool(at_lo or at_hi),
                    effective_complete_pooling=bool(at_hi),
                    extensions_lo=ext_lo, extensions_hi=ext_hi,
                    final_lo_exp=lo_exp, final_hi_exp=hi_exp, history=history)


# ================================================================ Stage 2 ridge
def block_ridge(X, y, block_of_column, alphas, fit_intercept=True):
    """Ridge with a SEPARATE penalty per block and an UNPENALIZED intercept.

        minimise  ||y - Xb - c||^2 + sum_k alpha_k * ||b_k||^2

    `block_of_column[j]` names column j's block; `alphas[block]` is its penalty.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float).ravel()
    n, p = X.shape
    if fit_intercept:
        Xd = np.hstack([np.ones((n, 1)), X])
        pen = np.array([0.0] + [float(alphas[block_of_column[j]]) for j in range(p)])
    else:
        Xd, pen = X, np.array([float(alphas[block_of_column[j]]) for j in range(p)])
    A = Xd.T @ Xd + np.diag(pen)
    coef = np.linalg.solve(A, Xd.T @ y)
    if fit_intercept:
        return float(coef[0]), coef[1:]
    return 0.0, coef


def select_alpha_pair(score_fn, lo_exp=-4.0, hi_exp=8.0):
    """JOINT two-dimensional selection over (alpha_caller, alpha_hc_context).

    `select_alpha` is one-dimensional and cannot express this: the two blocks are tuned TOGETHER
    because their penalties trade off against one another through the shared residual.

    TIE RULE (frozen, prereg v3.8) -- deterministic, and does not privilege either role:
      1. maximise log10(alpha_caller) + log10(alpha_hc_context)   (greatest TOTAL pooling)
      2. then the larger alpha_caller
      3. then the larger alpha_hc_context

    BOUNDARY RULE. Each coordinate extends INDEPENDENTLY by four decades at half-decade spacing,
    at most twice per coordinate per direction. When BOTH coordinates sit on a boundary they are
    extended in the SAME iteration. A persistent upper boundary marks effective complete pooling
    for THAT BLOCK ONLY.
    """
    c_lo, c_hi, h_lo, h_hi = lo_exp, hi_exp, lo_exp, hi_exp
    ext = {"caller_lo": 0, "caller_hi": 0, "hc_lo": 0, "hc_hi": 0}
    history = []

    while True:
        gc, gh = _grid(c_lo, c_hi), _grid(h_lo, h_hi)
        cand = []
        for ac in gc:
            for ah in gh:
                cand.append((float(ac), float(ah), float(score_fn(ac, ah))))
        history.append(dict(caller_lo=c_lo, caller_hi=c_hi, hc_lo=h_lo, hc_hi=h_hi,
                            candidates=[dict(alpha_caller=a, alpha_hc_context=b, score=s_)
                                        for a, b, s_ in cand]))
        assert any(np.isfinite(s_) for _a, _b, s_ in cand), (
            "every (alpha_caller, alpha_hc_context) pair scored non-finite -- the Stage 2 design "
            "or residual target contains NaN.")
        cand = [(a, b, s_ if np.isfinite(s_) else np.inf) for a, b, s_ in cand]
        best = min(s_ for _a, _b, s_ in cand)
        tied = [(a, b) for a, b, s_ in cand if s_ == best]
        # frozen three-step tie rule
        tied.sort(key=lambda t: (np.log10(t[0]) + np.log10(t[1]), t[0], t[1]))
        ac, ah = tied[-1]

        c_at_lo, c_at_hi = ac == gc[0], ac == gc[-1]
        h_at_lo, h_at_hi = ah == gh[0], ah == gh[-1]
        grew = False
        if c_at_lo and ext["caller_lo"] < MAX_EXTENSIONS_PER_DIRECTION:
            c_lo -= EXTEND_DECADES; ext["caller_lo"] += 1; grew = True
        elif c_at_hi and ext["caller_hi"] < MAX_EXTENSIONS_PER_DIRECTION:
            c_hi += EXTEND_DECADES; ext["caller_hi"] += 1; grew = True
        if h_at_lo and ext["hc_lo"] < MAX_EXTENSIONS_PER_DIRECTION:
            h_lo -= EXTEND_DECADES; ext["hc_lo"] += 1; grew = True
        elif h_at_hi and ext["hc_hi"] < MAX_EXTENSIONS_PER_DIRECTION:
            h_hi += EXTEND_DECADES; ext["hc_hi"] += 1; grew = True
        if grew:
            continue

        return dict(
            alpha_caller=float(ac), alpha_hc_context=float(ah), score=float(best),
            caller_at_lower=bool(c_at_lo), caller_at_upper=bool(c_at_hi),
            hc_at_lower=bool(h_at_lo), hc_at_upper=bool(h_at_hi),
            caller_complete_pooling=bool(c_at_hi), hc_complete_pooling=bool(h_at_hi),
            caller_boundary_unresolved=bool(c_at_lo or c_at_hi),
            hc_boundary_unresolved=bool(h_at_lo or h_at_hi),
            extensions=dict(ext), final_caller_lo=c_lo, final_caller_hi=c_hi,
            final_hc_lo=h_lo, final_hc_hi=h_hi, history=history)


def stage2_design(exposure_long, target_season, persons_caller=None, persons_ctx=None,
                  row_universe=None):
    """Identity design from historical exposures only (seasons < target_season).

    Columns are EXPOSURE FRACTIONS, one per (block, person). Unknown-caller games contribute to
    neither block, which is already true of `exposure_long` under the v3.6 rule.

    `row_universe` (season, team) is AUTHORITATIVE when supplied and MUST be the Stage 1 residual
    panel. Deriving keys from exposure rows silently DROPS every team-season whose caller is
    unknown -- exactly the rows the v3.6 neutral rule creates -- so those residuals would vanish
    from the fit instead of appearing as all-zero identity rows carrying the intercept.
    """
    e = exposure_long[exposure_long.season < target_season]
    cal = e[e.role == BR.ROLE_CALLER]
    ctx = e[e.role == BR.ROLE_HC_CTX]
    persons_caller = persons_caller if persons_caller is not None else sorted(
        cal.person_id.dropna().unique())
    persons_ctx = persons_ctx if persons_ctx is not None else sorted(
        ctx.person_id.dropna().unique())

    if row_universe is not None:
        keys = (row_universe[row_universe.season < target_season][["season", "team"]]
                .drop_duplicates().sort_values(["season", "team"]).reset_index(drop=True))
    else:
        keys = e[["season", "team"]].drop_duplicates().sort_values(["season", "team"])
        keys = keys.reset_index(drop=True)
    idx = {(s, t): i for i, (s, t) in enumerate(zip(keys.season, keys.team))}

    cols, names, blocks = [], [], []
    for label, sub, persons in [("caller", cal, persons_caller),
                                ("hc_context", ctx, persons_ctx)]:
        pos = {p: k for k, p in enumerate(persons)}
        M = np.zeros((len(keys), len(persons)))
        for r in sub.itertuples():
            if r.person_id in pos and (r.season, r.team) in idx:
                M[idx[(r.season, r.team)], pos[r.person_id]] = r.exposure
        cols.append(M)
        names += [f"{label}__{p}" for p in persons]
        blocks += [label] * len(persons)

    X = np.hstack(cols) if cols else np.zeros((len(keys), 0))
    assert X.min() >= 0.0 and X.max() <= 1.0 + 1e-12, "exposures must stay in [0, 1]"
    BR.assert_design_matrix_is_clean(names, "stage2")
    return keys, X, names, blocks
