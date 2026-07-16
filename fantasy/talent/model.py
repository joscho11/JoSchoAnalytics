"""Week-grain crossed FE model, sigma_alpha splits, and the R1 k derivation.

fit() is a verbatim port of the prototype solve (alpha + gamma_teamseason +
delta_opponent, weighted lsqr). sig() is the split-half sigma^2_alpha estimator,
NS and rng injected (R2). facet_stats() applies R3 (no floor — UNIDENTIFIABLE
flag) unless legacy floor mode is on for reproduction parity.

R1: sigma^2_eps(per-opportunity) = E[n_ptw * eps_ptw^2] over the model's
week-grain residuals; k_{P,f} = sigma^2_eps / sigma^2_alpha_median.
"""
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.linalg import lsqr


def _design(d, drop_delta=False):
    pf, pu = pd.factorize(d.pid); tf, tu = pd.factorize(d.ts); of, ou = pd.factorize(d.os)
    n = len(d); nP, nT, nO = len(pu), len(tu), len(ou)
    sw = np.sqrt(d.w.values); y = d.y.values * sw
    op, ot, oo = 1, 1 + (nP - 1), 1 + (nP - 1) + (nT - 1)
    ncol = 1 + (nP - 1) + (nT - 1) + ((nO - 1) if not drop_delta else 0)
    r = np.arange(n); Xr = [r]; Xc = [np.zeros(n, int)]; Xv = [sw]
    factors = [(pf, op), (tf, ot)] + ([] if drop_delta else [(of, oo)])
    for fac, off in factors:
        mm = fac > 0; Xr.append(r[mm]); Xc.append(off + fac[mm] - 1); Xv.append(sw[mm])
    X = sp.csr_matrix((np.concatenate(Xv), (np.concatenate(Xr), np.concatenate(Xc))),
                      shape=(n, ncol))
    return X, y, sw, pf, pu, op, nP


def fit(df, drop_delta=False):
    d = df.reset_index(drop=True)
    X, y, sw, pf, pu, op, nP = _design(d, drop_delta)
    sol = lsqr(X, y, atol=1e-8, btol=1e-8, iter_lim=20000)[0]
    a = np.zeros(nP); a[1:] = sol[op:op + nP - 1]
    a = a - np.average(a, weights=np.bincount(pf, d.w.values))
    return pu, a, np.bincount(pf, d.w.values)


def sigma2_eps(df, drop_delta=False):
    """R1: E[n_ptw * eps^2] with n_ptw = the week's raw opportunity count `o`."""
    d = df.reset_index(drop=True)
    X, y, sw, pf, pu, op, nP = _design(d, drop_delta)
    sol = lsqr(X, y, atol=1e-8, btol=1e-8, iter_lim=20000)[0]
    eps = (y - X @ sol) / sw          # unweighted week-grain residual
    return float(np.mean(d.o.values * eps ** 2))


def sig(df, rng, ns):
    """Split-half sigma^2_alpha samples (the prototype estimator, NS injected)."""
    cs = []
    for _ in range(ns):
        d = df.reset_index(drop=True); h = rng.random(len(d)) < 0.5
        pa, aa, na = fit(d[h]); pb, ab, nb = fit(d[~h])
        ma = dict(zip(pa, aa)); mb = dict(zip(pb, ab))
        na = dict(zip(pa, na)); nb = dict(zip(pb, nb))
        c = [p for p in ma if p in mb]
        if len(c) >= 8:
            cs.append(np.cov([ma[p] for p in c], [mb[p] for p in c],
                             aweights=[min(na[p], nb[p]) for p in c])[0, 1])
    return np.array(cs)


def facet_stats(cs, floor):
    """Gate-6 quartet. floor=True reproduces the prototype's 1e-4 clip (legacy
    parity ONLY); floor=False is R3 — no clip, UNIDENTIFIABLE flag on median<=0."""
    med, mean = float(np.median(cs)), float(cs.mean())
    out = dict(s2a_med=med, s2a_mean=mean, cs_std=float(cs.std()),
               cv=float(cs.std() / abs(cs.mean())) if cs.mean() != 0 else 0.0,
               le0=float((cs <= 0).mean()), n_splits=len(cs), unidentifiable=False)
    if floor:
        out["sam"] = float(np.sqrt(max(mean, 1e-4)))
        out["sad"] = float(np.sqrt(max(med, 1e-4)))
    else:
        if med <= 0:
            out["unidentifiable"] = True
            out["sam"] = out["sad"] = float("nan")
        else:
            out["sad"] = float(np.sqrt(med))
            out["sam"] = float(np.sqrt(mean)) if mean > 0 else float("nan")
    return out


# ---- QB MoM (no model) ------------------------------------------------------

def sig_mom(rows, rng, ns):
    """Split-half sigma^2_alpha for a MoM facet from row-level (pid, v, wgt)."""
    pid = rows.pid.values; xv = (rows.v * rows.wgt).values; wv = rows.wgt.values
    cs = []
    for _ in range(ns):
        h = rng.random(len(rows)) < 0.5
        fa = pd.DataFrame({"x": xv[h], "n": wv[h]}).groupby(pid[h]).sum()
        fb = pd.DataFrame({"x": xv[~h], "n": wv[~h]}).groupby(pid[~h]).sum()
        c = fa.index.intersection(fb.index)
        if len(c) >= 8:
            ma = (fa.x / fa.n).loc[c]; mb = (fb.x / fb.n).loc[c]
            aw = np.minimum(fa.n.loc[c].values, fb.n.loc[c].values)
            cs.append(np.cov(ma.values, mb.values, aweights=aw)[0, 1])
    return np.array(cs)


def s2eps_mom(rows, grain):
    """Pooled within-player per-opportunity variance.
    grain='play': rows are single opportunities -> groupby var, mean (qb2 recipe).
    grain='agg' : rows are aggregates with `att` -> E[att*(v-vbar)^2]*n/(n-1)."""
    if grain == "play":
        return float(rows.groupby("pid").v.var().mean())
    parts = []
    for _, g in rows.groupby("pid"):
        if len(g) < 2:
            continue
        vbar = np.average(g.v, weights=g.att)
        parts.append(np.sum(g.att * (g.v - vbar) ** 2) / (len(g) - 1))
    return float(np.mean(parts))
