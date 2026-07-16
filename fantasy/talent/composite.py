"""Composite, boards, constrained-Bayes anchor, RB pipe.

ONE composite branch (R5): contribution = w_f * z_f for every position. In
reproduction mode the legacy QB branch (D[f] = z, sqrt(w) baked into z) is kept
for prototype parity only. PERCENTILE NOWHERE (np.percentile below is the
two-point CB anchor spec, not a player transform; report-only percentiles live
in report scripts).
"""
import re
import numpy as np
import pandas as pd

from config import WEIGHTS, ANCHOR, RHO_RB_BOX_DISATT
from schemas import SchemaError, stable_rank_sort


def norm_simple(s):
    s = re.sub(r"\b(iii|ii|iv|jr|sr)\b", "", str(s).lower())
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def scored_universe(board, sd, P):
    return set(board[board.position == P].player_id) | set(
        sd[(sd.position == P) & (sd.adp_overall_rank <= 250)].player_id)


def build_boards(F, board, sd, names, qb_mode, rz_rb=None, gname=None, weights=None):
    """F[P][facet] = DataFrame(index=pid) with z, w. Returns scored boards.
    weights defaults to the live OWNER CONFIG; the reproduce/verify path passes
    the PROTOTYPE vectors (the accepted table's basis) explicitly."""
    W = weights or WEIGHTS
    out, anchors, audits = {}, {}, {}
    for P in W:
        facs = [f for f in W[P] if f in F[P]]
        idx = sorted(set().union(*[set(F[P][f].index) for f in facs]))
        D = pd.DataFrame(index=idx)
        for f in facs:
            z = F[P][f]["z"].reindex(D.index).fillna(0)
            w = F[P][f]["w"].reindex(D.index).fillna(0)
            D[f + "z"] = z; D[f + "w"] = w
            if P == "QB" and qb_mode == "legacy":
                D[f] = z                      # legacy parity branch only
            else:
                D[f] = w * z                  # the ONE branch (R5)
        D["pm"] = sum(W[P][f] * D[f] for f in facs)
        D["w"] = sum(W[P][f] * D[f + "w"] for f in facs) / sum(
            W[P][f] for f in facs)
        D["cb"] = D.pm / D.pm.std()
        U = scored_universe(board, sd, P)
        S = D[D.index.isin(U)].copy()
        sl = S[S.w >= ANCHOR["anchor_min_w"]].cb
        if len(sl) < 10:
            raise SchemaError(f"{P}: anchor slice (w>={ANCHOR['anchor_min_w']}) has "
                              f"only {len(sl)} players — cannot anchor")
        z2, z98 = np.percentile(sl, [ANCHOR["lo_pct"], ANCHOR["hi_pct"]])
        if not z98 > z2:
            raise SchemaError(f"{P}: degenerate anchor (p{ANCHOR['hi_pct']}<=p{ANCHOR['lo_pct']})")
        B = (ANCHOR["hi_score"] - ANCHOR["lo_score"]) / (z98 - z2)
        a = ANCHOR["lo_score"] - B * z2
        S["cb_nfl"] = S.cb
        S["college_share"] = 0.0
        if P == "RB" and rz_rb is not None:
            audit = {}
            rz = pd.Series(index=S.index, dtype=float)
            byname = {}
            for pid in S.index:
                nm = (gname or {}).get(pid) or norm_simple(names.get(pid, ""))
                byname.setdefault(nm, []).append(pid)
                if nm in rz_rb:
                    rz[pid] = rz_rb[nm]
            audits[P] = {nm: pids for nm, pids in byname.items() if len(pids) > 1}
            has = rz.notna()
            S["cb"] = S.cb_nfl + np.where(has, (1 - S.w) * RHO_RB_BOX_DISATT * rz.fillna(0), 0.0)
            S["college_share"] = np.where(has, (1 - S.w) * RHO_RB_BOX_DISATT, 0.0)
        S["score"] = np.clip(a + B * S.cb, *ANCHOR["clip"])
        S["se"] = B * np.where(S.w > 0, np.sqrt(np.clip((1 - S.w) / S.w, 0, None)), 2.2)
        S["nm"] = [names.get(p, p) for p in S.index]
        out[P] = stable_rank_sort(S)   # deterministic; 3c near-ties by confidence
        anchors[P] = (a, B)
    return out, anchors, audits


def eff_shares(S, P, weights=None):
    """share_f = W_f*Cov(c_f,pm)/Var(pm), ddof=0, scored universe; sums to 1."""
    W = weights or WEIGHTS
    facs = [f for f in W[P] if f + "z" in S.columns]
    pm = S["pm"].values

    def popcov(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        return np.mean((x - x.mean()) * (y - y.mean()))

    vp = popcov(pm, pm)
    return {f: W[P][f] * popcov(S[f].values, pm) / vp for f in facs}
