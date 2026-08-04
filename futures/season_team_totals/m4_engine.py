"""M4 game-level margin model + schedule Monte Carlo — the shared engine.

WHY THIS IS A MODULE (2026-08-03)
---------------------------------
`03_distribution_model.ipynb` evaluated M4/M4-c and `04_fit_production.ipynb` fits the shipped
artifact. Two copies of the same estimator would drift, and the production model would stop being
the thing that was evaluated. This module is the single implementation; `04` imports it and
**proves** it reproduces `03`'s recorded per-fold constants exactly before fitting anything.

Same carve-out as `tier_lock.py`: a contract several notebooks depend on is imported, not
reconstructed. See `memory/prefer-ipynb-not-py.md`.

MODEL
-----
Game-level margin, fitted on training seasons only:

    home_margin = beta . (x_home - x_away) + hfa * hfa_mult + eps,   eps ~ N(0, sigma^2)

* The design is **differenced and antisymmetric**, so swapping the teams negates the prediction and
  home advantage can only enter through its own column.
* `hfa_mult` is 0 for explicit-neutral or international games (PREREGISTRATION A2.5.6) and 1
  otherwise, so home field is switchable per game.
* A team's rating is the same linear function applied to its own features.

M4-c (Amendment 3) adds a per-team-season strength shock `eps_team ~ N(0, tau^2)` drawn once per
team per simulated season and applied to every game that team plays — it helps that team and hurts
its opponent by the same amount, so league wins stay conserved.

FAITHFUL-REPRODUCTION NOTE
--------------------------
`tie_rate` is supplied by the caller. `03` computed it as `(games.result == 0).mean()` over the
windowed schedule, whose denominator includes the *unplayed* predict season (272 rows in 2026).
That understates the tie rate by ~4% relative to played games only. The effect is negligible (ties
are ~0.23% of games) but the parameter is passed in rather than recomputed so `04` can reproduce
`03`'s constants exactly instead of approximately.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

__all__ = ["game_design", "fit_margin", "design_matrix", "predict_mu", "simulate_wins",
           "inner_folds", "select_alpha", "select_tau", "TAU_GRID", "TAU_FALLBACK"]

TAU_GRID = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)      # A3.3, frozen
TAU_FALLBACK = 1.5


def inner_folds(seasons):
    """Expanding-season inner folds: validate on S_i, train on S_1..S_{i-1}."""
    s = sorted({int(x) for x in seasons})
    return [(s[:i], s[i]) for i in range(1, len(s))]


def game_design(games: pd.DataFrame, feat: pd.DataFrame, seasons, features,
                settled_only: bool = True):
    """Return (g, X) for `seasons`. X is the antisymmetric home-minus-away feature difference."""
    m = games["season"].isin(list(seasons))
    if settled_only:
        m &= games["result"].notna()
    g = games[m].copy()
    h = feat.reindex(pd.MultiIndex.from_arrays([g["season"], g["home_franchise"]]))
    a = feat.reindex(pd.MultiIndex.from_arrays([g["season"], g["away_franchise"]]))
    return g, pd.DataFrame(h.to_numpy() - a.to_numpy(), columns=list(features), index=g.index)


def fit_margin(g: pd.DataFrame, X: pd.DataFrame, alpha: float, tie_rate: float) -> dict:
    """Fit the margin model on the supplied games. Imputer and scaler are fitted here, so a
    caller that passes only training rows gets a training-only fit by construction."""
    imp = SimpleImputer(strategy="median").fit(X)
    sc = StandardScaler().fit(imp.transform(X))
    Z = np.column_stack([sc.transform(imp.transform(X)), g["hfa_mult"].to_numpy()])
    model = Ridge(alpha=alpha, fit_intercept=False).fit(Z, g["result"].to_numpy())
    resid = g["result"].to_numpy() - model.predict(Z)
    return {"imp": imp, "sc": sc, "model": model,
            "sigma": float(resid.std(ddof=1)),
            "hfa": float(model.coef_[-1]),
            "tie_thr": float(np.quantile(np.abs(resid), tie_rate)),
            "alpha": float(alpha), "n_train_games": int(len(g))}


def design_matrix(fit: dict, X: pd.DataFrame, hfa_mult) -> np.ndarray:
    return np.column_stack([fit["sc"].transform(fit["imp"].transform(X)), np.asarray(hfa_mult, float)])


def predict_mu(fit: dict, X: pd.DataFrame, hfa_mult) -> np.ndarray:
    return fit["model"].predict(design_matrix(fit, X, hfa_mult))


def simulate_wins(fit: dict, g: pd.DataFrame, X: pd.DataFrame, n_sims: int, seed: int,
                  tau: float = 0.0) -> pd.DataFrame:
    """Simulate `n_sims` seasons of the games in `g`. Returns (n_sims x teams) win counts.

    League wins are conserved in every simulation: each game awards exactly 1.0 across the two
    participants (0.5 + 0.5 on a tie), and the tau shock is antisymmetric within a game.
    """
    mu = predict_mu(fit, X, g["hfa_mult"].to_numpy())
    teams = sorted(set(g["home_franchise"]) | set(g["away_franchise"]))
    tix = {t: i for i, t in enumerate(teams)}
    H = np.zeros((len(g), len(teams)))
    A = np.zeros((len(g), len(teams)))
    H[np.arange(len(g)), [tix[t] for t in g["home_franchise"]]] = 1.0
    A[np.arange(len(g)), [tix[t] for t in g["away_franchise"]]] = 1.0

    rng = np.random.default_rng(seed)
    draws = rng.normal(mu, fit["sigma"], size=(n_sims, len(g)))
    if tau > 0:
        eps = rng.normal(0.0, tau, size=(n_sims, len(teams)))
        draws = draws + eps @ H.T - eps @ A.T
    thr = fit["tie_thr"]
    home_pts = np.where(draws > thr, 1.0, np.where(draws < -thr, 0.0, 0.5))
    return pd.DataFrame(home_pts @ H + (1.0 - home_pts) @ A, columns=teams)


def select_alpha(games, feat, features, train_seasons, tie_rate, alpha_grid,
                 fallback_alpha, n_inner=6):
    """Alpha by inner expanding-season validation inside the training window only."""
    folds = inner_folds(train_seasons)
    if len(folds) < 2:
        return float(fallback_alpha), True, {}
    scores = {}
    for a in alpha_grid:
        errs = []
        for tr_s, va_s in folds[-n_inner:]:
            g_tr, X_tr = game_design(games, feat, tr_s, features)
            f = fit_margin(g_tr, X_tr, a, tie_rate)
            g_va, X_va = game_design(games, feat, [va_s], features)
            errs.append(float(np.abs(predict_mu(f, X_va, g_va["hfa_mult"].to_numpy())
                                     - g_va["result"].to_numpy()).mean()))
        scores[a] = float(np.mean(errs))
    return float(min(scores, key=lambda a: (scores[a], a))), False, scores


def select_tau(games, feat, features, train_seasons, tie_rate, alpha, panel, target,
               n_sims=4000, seed=0, n_inner=3, tau_grid=TAU_GRID, fallback=TAU_FALLBACK):
    """Tau by inner expanding-season validation inside the training window only (A3.3):
    minimise |inner coverage80 - 0.80|, smallest tau on ties."""
    folds = inner_folds(train_seasons)
    if len(folds) < 2:
        return float(fallback), True, {}
    scores = {}
    for tau in tau_grid:
        covs = []
        for tr_s, va_s in folds[-n_inner:]:
            g_tr, X_tr = game_design(games, feat, tr_s, features)
            f = fit_margin(g_tr, X_tr, alpha, tie_rate)
            g_va, X_va = game_design(games, feat, [va_s], features, settled_only=False)
            s = simulate_wins(f, g_va, X_va, n_sims=n_sims, seed=seed + int(va_s), tau=tau)
            ev = panel[(panel["season"] == va_s) & panel["has_target"]]
            lo, hi = s.quantile(.10), s.quantile(.90)
            covs.append(float(np.mean([bool(lo[r["franchise"]] <= r[target] <= hi[r["franchise"]])
                                       for _, r in ev.iterrows() if r["franchise"] in s.columns])))
        scores[tau] = float(np.mean(covs))
    best = min(tau_grid, key=lambda t: (abs(scores[t] - 0.80), t))
    return float(best), False, scores
