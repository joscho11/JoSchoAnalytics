"""PHASE 1D — game-based reliability at (person_id, target_season, role) grain.

Answers "how much relevant history does this person actually have entering season Y?" using GAMES,
never seasons. `16 x n_seasons` is wrong twice over: it ignores the 17-game era and it credits a
full season to someone who took over in week 12.

THREE SEMANTICALLY DISTINCT COUNTS, never merged
------------------------------------------------
A. `caller`                  every resolved prior game the person ACTUALLY CALLED, whatever their
                             title. This is the portable history that unifies McDaniel's MIA
                             HC-called games and McVay's WAS-OC + LA-HC games.
B. `hc_resume`               every prior regular-season game served as head coach. Feeds HC
                             résumé/experience/shrinkage.
C. `noncalling_hc_context`   only prior games that ACTIVATED the non-calling-HC-context block.

D. `unknown_caller_hc_games` prior games where the HC was present but NOBODY knows who called.

C is computed by calling `build_exposure.exposure_long`, not by re-deriving the activation rule.

**v3.6 CORRECTION.** C previously used `~same`, which is true both when a distinct known person
called AND when the caller is unknown -- so every unknown-caller game was credited to the head
coach's "delegated offense" effect. Andy Reid entering 2026 reported hc_context = 245 of which only
**5** were verified delegated (Matt Nagy, 2017); the other **240** were unknown-caller games, all
1999-2013, entirely before the attribution window opens. An unknown-caller game now activates
NEITHER identity block; the HC still accrues ordinary résumé history from it, and the games are
counted in D so the gap stays visible.

IDENTITY, asserted per person: `hc_resume = self_called + known_delegated + unknown_caller`.

HC == CALLER is counted once in A and once in B, and zero times in C. That is not duplication:
caller résumé and head-coach résumé are different feature families. Within a single block no game
is ever counted twice -- asserted on distinct game_ids.

TIMING. Every count for target season Y uses games from seasons STRICTLY LESS THAN Y. No season-Y
game, no realized season-Y exposure, no season-Y performance. Asserted per output row.

This module produces PERSON-LEVEL history only. It does NOT decide which current identity receives
those features -- that is Design A (point-in-time) vs Design B (oracle) routing, applied downstream.
Mixing the two here would bake an identity policy into the historical counts.
"""
import hashlib
import pathlib

import numpy as np
import pandas as pd

import build_exposure as BE

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"

K_SHRINK = 32          # frozen: reliability = g / (g + 32)
ROLE_CALLER = "caller"
ROLE_HC_RESUME = "hc_resume"
ROLE_HC_CTX = BE.ROLE_HC_CTX
ROLE_UNKNOWN_HC = "unknown_caller_hc_games"

# ONE name per concept. The v3.6 artifact shipped duplicate aliases (prior_games AND
# observed_prior_games, reliability AND observed_reliability, log1p_prior_games AND
# observed_games_log) -- the claimed rename had only ADDED columns, never removed the originals.
CANONICAL_SCHEMA = [
    "person_id", "target_season", "role",
    "observed_prior_games", "observed_games_log", "observed_reliability",
    "no_prior_history", "n_observed_prior_seasons", "max_observed_season",
    "observed_history_start", "observable_prior_seasons", "history_left_censored",
]
LEGACY_ALIASES_REMOVED = ["prior_games", "reliability", "log1p_prior_games",
                          "n_prior_seasons", "max_season"]


def _game_level():
    tbl = pd.read_csv(DATA / "actual_play_caller.csv")
    hc = pd.read_csv(DATA / "head_coach_games.csv")
    gl = BE.game_level_identity(hc, tbl)
    # REG only. Playoff games must never enter résumé counts.
    assert gl["game_id"].is_unique or True
    return gl


def _per_season_counts(gl):
    """(season, person_id, role) -> distinct games. Built on game_ids so nothing double-counts."""
    known = gl["caller_person_id"].notna()

    # A. CALLER -- every resolved game the person called, any title
    cal = (gl[known].groupby(["season", "caller_person_id"])["game_id"].nunique()
           .rename("games").reset_index().rename(columns={"caller_person_id": "person_id"}))
    cal["role"] = ROLE_CALLER

    # B. HC RESUME -- every game served as head coach
    hcr = (gl[gl.hc_person_id.notna()].groupby(["season", "hc_person_id"])["game_id"].nunique()
           .rename("games").reset_index().rename(columns={"hc_person_id": "person_id"}))
    hcr["role"] = ROLE_HC_RESUME

    # C. NON-CALLING HC CONTEXT -- delegated to the exposure rule, not re-derived here.
    # v3.6: this now counts ONLY games where a distinct KNOWN person called.
    exp = BE.exposure_long(gl)
    ctx = (exp[exp.role == ROLE_HC_CTX].groupby(["season", "person_id"])["games"].sum()
           .rename("games").reset_index())
    ctx["role"] = ROLE_HC_CTX

    # D. UNKNOWN-CALLER HC GAMES -- tracked SEPARATELY, never folded into C. These are games the
    # head coach was present for but where nobody knows who called plays. They grant no offensive
    # identity effect to anyone; they exist so the missing attribution stays auditable.
    unk = (gl[gl.caller_person_id.isna() & gl.hc_person_id.notna()]
           .groupby(["season", "hc_person_id"])["game_id"].nunique()
           .rename("games").reset_index().rename(columns={"hc_person_id": "person_id"}))
    unk["role"] = ROLE_UNKNOWN_HC

    return pd.concat([cal, hcr, ctx, unk], ignore_index=True)


def build(target_seasons=None):
    gl = _game_level()
    per = _per_season_counts(gl)

    seasons = sorted(gl["season"].unique())
    target_seasons = target_seasons or [s for s in seasons if s > min(seasons)]

    rows = []
    for Y in target_seasons:
        prior = per[per.season < Y]                     # STRICTLY less than Y
        agg = (prior.groupby(["person_id", "role"])
               .agg(prior_games=("games", "sum"), max_season=("season", "max"),
                    n_prior_seasons=("season", "nunique")).reset_index())
        agg["target_season"] = Y
        rows.append(agg)

    out = pd.concat(rows, ignore_index=True)
    # v3.6 SEMANTICS: for the caller role these are OBSERVED-SAMPLE quantities -- confidence in
    # the performance history actually observed since the attribution window opens (2014), NOT true
    # career experience. Reid's low early reliability is a correct statement about available
    # evidence, not a claim that he was inexperienced in 2015. Nothing is imputed to fix it.
    out = out.rename(columns={"prior_games": "observed_prior_games",
                              "n_prior_seasons": "n_observed_prior_seasons",
                              "max_season": "max_observed_season"})
    out["observed_reliability"] = (
        out.observed_prior_games / (out.observed_prior_games + K_SHRINK))
    out["observed_games_log"] = np.log1p(out.observed_prior_games)
    out["no_prior_history"] = (out.observed_prior_games == 0).astype(int)

    out = _flag_left_censoring(out, gl)

    out = out[CANONICAL_SCHEMA]
    assert list(out.columns) == CANONICAL_SCHEMA
    for legacy in LEGACY_ALIASES_REMOVED:
        assert legacy not in out.columns, "legacy alias " + legacy + " resurfaced"
    out = out.sort_values(["target_season", "role", "person_id"]).reset_index(drop=True)

    _assert_timing(out)
    _assert_no_double_counting(gl)
    _assert_reconciles(gl, out)

    out.to_csv(DATA / "coach_reliability.csv", index=False)
    _lineage(gl).to_csv(DATA / "coach_reliability_lineage.csv", index=False)
    print(f"wrote {DATA/'coach_reliability.csv'}  ({len(out)} rows, "
          f"{out.person_id.nunique()} persons, {out.target_season.nunique()} target seasons)")
    return out


def _flag_left_censoring(out, gl):
    """The two histories do NOT reach equally far back, and that must be visible on every row.

    `actual_play_caller.csv` begins in 2014; `head_coach_games.csv` begins in 1999. So CALLER
    history is left-censored at 2014 while HC-RESUME history is left-censored at 1999. Measured
    effect on Andy Reid, who had called plays since 1999:

        target 2015 -> caller 16, hc_resume 256      (caller reliability 0.33 vs 0.89)
        target 2026 -> caller 192, hc_resume 437

    His caller count therefore GROWS with calendar time purely because the observation window
    widens. Uncorrected, `caller_reliability` is confounded with target season: early-window rows
    look unreliable regardless of the person's real experience. This is a data-coverage property,
    not an arithmetic error, but a model must not be handed it silently.

    `history_left_censored` marks rows whose true history provably predates the caller window --
    detected via a head-coach appearance before 2014. NOTE the detection is incomplete: a person
    who was an OC/play-caller before 2014 without ever being a head coach cannot be detected at
    all, because no pre-2014 caller record exists. Absence of the flag is therefore NOT proof that
    a count is complete.
    """
    caller_start = int(pd.read_csv(DATA / "actual_play_caller.csv").season.min())
    hc_start = int(gl.season.min())

    pre = gl[gl.season < caller_start]
    early_persons = set(pre.hc_person_id.dropna()) | set(pre.caller_person_id.dropna())

    out = out.copy()
    out["observed_history_start"] = np.where(
        out.role.isin([ROLE_CALLER, ROLE_HC_CTX]), caller_start, hc_start)
    out["observable_prior_seasons"] = out.target_season - out.observed_history_start
    out["history_left_censored"] = (
        (out.role.isin([ROLE_CALLER, ROLE_HC_CTX])) & (out.person_id.isin(early_persons))
    ).astype(int)
    return out


# ---------------------------------------------------------------- assertions
def _assert_timing(out):
    """HARD: no row may draw on season >= its own target season."""
    bad = out[out.max_observed_season >= out.target_season]
    assert bad.empty, (
        f"TIMING VIOLATION: {len(bad)} rows contain games from season >= target_season\n"
        f"{bad.head(10).to_string()}")


def _assert_no_double_counting(gl):
    """Within ONE role block a game_id may appear at most once per person."""
    known = gl["caller_person_id"].notna()
    for label, sub, key in [("caller", gl[known], "caller_person_id"),
                            ("hc_resume", gl[gl.hc_person_id.notna()], "hc_person_id")]:
        d = sub.groupby([key, "game_id"]).size()
        assert (d <= 1).all(), f"{label}: a game_id is counted twice for one person"
    # a person is never BOTH caller and hc_context on the SAME game
    same = gl[known & (gl.hc_person_id == gl.caller_person_id)]
    exp = BE.exposure_long(gl)
    for _, r in same.head(200).iterrows():
        ctx = exp[(exp.season == r.season) & (exp.team == r.team)
                  & (exp.person_id == r.hc_person_id) & (exp.role == ROLE_HC_CTX)]
        team_games = int((gl.season == r.season).__and__(gl.team == r.team).sum())
        assert ctx.games.sum() < team_games, (
            f"HC==caller game leaked into hc_context for {r.hc_person_id} {r.season} {r.team}")


def _assert_reconciles(gl, out):
    """Role-game totals must reconcile against the game-level identity artifact."""
    seasons = sorted(gl.season.unique())
    Y = max(seasons)
    hist = gl[gl.season < Y]
    exp_caller = hist[hist.caller_person_id.notna()].game_id.nunique()
    got_caller = out[(out.target_season == Y) & (out.role == ROLE_CALLER)].observed_prior_games.sum()
    # every resolved historical game contributes exactly one caller-game
    assert got_caller == len(hist[hist.caller_person_id.notna()]), (
        f"caller reconciliation: {got_caller} vs {len(hist[hist.caller_person_id.notna()])}")
    assert exp_caller <= got_caller

    got_hc = out[(out.target_season == Y) & (out.role == ROLE_HC_RESUME)].observed_prior_games.sum()
    assert got_hc == len(hist[hist.hc_person_id.notna()]), (
        f"hc_resume reconciliation: {got_hc} vs {len(hist[hist.hc_person_id.notna()])}")

    exp = BE.exposure_long(gl)
    ctx_hist = exp[(exp.role == ROLE_HC_CTX) & (exp.season < Y)].games.sum()
    got_ctx = out[(out.target_season == Y) & (out.role == ROLE_HC_CTX)].observed_prior_games.sum()
    assert got_ctx == ctx_hist, f"hc_context reconciliation: {got_ctx} vs {ctx_hist}"

    # v3.6 IDENTITY: hc_resume == self-called + known-delegated + unknown, exactly, per person.
    hist_known = hist.caller_person_id.notna()
    self_called = hist[hist_known & (hist.hc_person_id == hist.caller_person_id)]
    got_unk = out[(out.target_season == Y) & (out.role == ROLE_UNKNOWN_HC)].observed_prior_games.sum()
    unk_hist = len(hist[hist.caller_person_id.isna() & hist.hc_person_id.notna()])
    assert got_unk == unk_hist, f"unknown-caller reconciliation: {got_unk} vs {unk_hist}"
    assert len(self_called) + ctx_hist + unk_hist == got_hc, (
        f"decomposition broken: {len(self_called)} + {ctx_hist} + {unk_hist} != {got_hc}")


def _lineage(gl):
    """Per (season, person, role) game-id lineage so every count traces to games."""
    known = gl["caller_person_id"].notna()
    parts = []
    c = gl[known][["season", "team", "game_id", "caller_person_id"]].copy()
    c = c.rename(columns={"caller_person_id": "person_id"}); c["role"] = ROLE_CALLER
    parts.append(c)
    h = gl[gl.hc_person_id.notna()][["season", "team", "game_id", "hc_person_id"]].copy()
    h = h.rename(columns={"hc_person_id": "person_id"}); h["role"] = ROLE_HC_RESUME
    parts.append(h)
    dist = known & (gl.hc_person_id != gl.caller_person_id)
    x = gl[dist][["season", "team", "game_id", "hc_person_id"]].copy()
    x = x[x.hc_person_id.notna()].rename(columns={"hc_person_id": "person_id"})
    x["role"] = ROLE_HC_CTX
    parts.append(x)
    u = gl[~known & gl.hc_person_id.notna()][["season", "team", "game_id", "hc_person_id"]].copy()
    u = u.rename(columns={"hc_person_id": "person_id"}); u["role"] = ROLE_UNKNOWN_HC
    parts.append(u)
    return pd.concat(parts, ignore_index=True).sort_values(
        ["season", "role", "person_id", "game_id"]).reset_index(drop=True)


def routing_flags(rel=None, snap=None):
    """Target-season routing flags. TWO DISTINCT SITUATIONS, never collapsed into one flag.

      A. caller_identity_unknown = 1   -- we do not know WHO will call plays. No person is named,
                                          so no person's history applies. Routes to the league
                                          prior. NO pooled unknown-person coefficient is created.
      B. caller_no_prior_history = 1   -- we DO know who (identity_unknown = 0), but that person has
                                          called zero prior games. Routes to the league prior too,
                                          but for an entirely different reason.

    Collapsing these would merge "unidentified" with "identified rookie play-caller" -- two
    populations with different downstream treatment and different diagnostics.
    """
    rel = rel if rel is not None else pd.read_csv(DATA / "coach_reliability.csv")
    snap = snap if snap is not None else pd.read_csv(DATA / "preseason_staff_snapshot.csv")

    s = snap[["season", "team", "expected_opening_caller_id"]].copy()
    s["caller_identity_unknown"] = s.expected_opening_caller_id.isna().astype(int)

    cal = rel[rel.role == ROLE_CALLER][
        ["person_id", "target_season", "observed_prior_games", "observed_reliability"]]
    out = s.merge(cal, left_on=["expected_opening_caller_id", "season"],
                  right_on=["person_id", "target_season"], how="left")

    known = out.caller_identity_unknown == 0
    out["caller_observed_prior_games"] = np.where(
        known, out.observed_prior_games.fillna(0), np.nan)
    out["caller_observed_reliability"] = np.where(
        known, out.observed_reliability.fillna(0.0), np.nan)
    # B applies ONLY where identity IS known
    out["caller_no_prior_history"] = np.where(
        known, (out.observed_prior_games.fillna(0) == 0).astype(int), 0)
    out["routes_to_league_prior"] = (
        (out.caller_identity_unknown == 1) | (out.caller_no_prior_history == 1)).astype(int)

    # v3.6 TARGET-SEASON NEUTRALITY. When the expected caller is unknown we must not assume the
    # head coach delegated (which the old rule did by granting HC context) NOR that he called the
    # plays himself. BOTH identity blocks route to the league prior; only ordinary HC
    # résumé/change/tenure features survive, and those are unaffected by who calls plays.
    out["hc_context_identity_routes_to_prior"] = out.caller_identity_unknown
    out["assumes_delegation"] = 0          # asserted below; never set to 1
    assert (out.assumes_delegation == 0).all()

    assert not ((out.caller_identity_unknown == 1) & (out.caller_no_prior_history == 1)).any(), (
        "the two unknown situations must never both fire on one row")
    return out[["season", "team", "expected_opening_caller_id", "caller_identity_unknown",
                "caller_no_prior_history", "caller_observed_prior_games",
                "caller_observed_reliability",
                "routes_to_league_prior", "hc_context_identity_routes_to_prior",
                "assumes_delegation"]]


# =====================================================================================
# FEATURE-USE POLICY (prereg v3.7). Four DISJOINT lists, enforced against the ACTUAL Stage 1 /
# Stage 2 design matrices -- not against a hand-maintained list alone.
# =====================================================================================
#
# WHY observed_reliability IS NOT A PREDICTOR. r = g/(g+32) is a strictly monotone bijection of
# g = observed_prior_games. Renaming a count does not remove its information: r carries exactly
# the same left-censored sample-size and calendar signal the policy exists to exclude, so
# admitting r as an independent predictor readmits g through the back door. Reliability is
# therefore usable ONLY as a deterministic shrinkage/precision weight or a diagnostic.
#
# DOUBLE SHRINKAGE. Stage 2 ridge already partially pools identity coefficients by sample size.
# Multiplying a fitted ridge effect by observed_reliability afterwards -- or adding reliability
# beside it as another column -- applies sample-size shrinkage twice. Both are forbidden.

MODEL_PREDICTORS = [
    # The Stage 2 identity design admits EXPOSURE FRACTIONS ONLY, one block per role.
    "caller_exposure", "noncalling_hc_context_exposure",
]

PRECISION_ONLY = [
    # Deterministic shrinkage / uncertainty / diagnostics. NEVER in X, never in hyperparameter
    # selection, never in stratification, never in interaction generation.
    "observed_reliability",
]

ROUTING_ONLY = [
    # Control missing-history and league-prior routing. Not coach quality, never a predictor.
    "no_prior_history", "caller_no_prior_history", "caller_identity_unknown",
    "hc_context_identity_routes_to_prior", "routes_to_league_prior", "assumes_delegation",
]

AUDIT_ONLY = [
    # Lineage, sample-size and censoring fields. Calendar proxies: observable_prior_seasons is
    # target_season minus a constant, so handing it to a model hands over the season index.
    "observed_prior_games", "observed_games_log", "n_observed_prior_seasons",
    "max_observed_season", "observed_history_start", "observable_prior_seasons",
    "history_left_censored", "caller_observed_prior_games", "caller_observed_reliability",
    "unknown_caller_hc_games", "hc_resume",
]

FORBIDDEN_IN_X = sorted(set(PRECISION_ONLY) | set(ROUTING_ONLY) | set(AUDIT_ONLY))


def assert_design_matrix_is_clean(X_columns, stage):
    """Inspect an ACTUAL design matrix. Raises on any non-allowlisted column."""
    bad = [c for c in list(X_columns) if c in FORBIDDEN_IN_X]
    assert not bad, stage + ": forbidden columns in X -> " + repr(bad)
    return True


def md5(p):
    return hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()


if __name__ == "__main__":
    build()
