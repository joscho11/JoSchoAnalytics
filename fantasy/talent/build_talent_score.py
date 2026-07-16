"""Talent Score build orchestrator (Phase 1).

Stages (checkpointed under C:/tmp/talent_build/):
  facets            heavy nflreadpy loads -> FACETS.pkl
  model  --mode M   sigma_alpha at NS splits, k (legacy|derived), z -> MODEL_{M}.pkl
  board  --mode M   composite/boards/eff-shares -> BOARD_{M}.pkl
  verify            reproduce-mode regression vs the ACCEPTED table (printed precision)
  delta             old (reproduce) vs new (ruled) per facet + QB decile test

Reproduce-then-upgrade protocol: `model --mode reproduce` must pass `verify`
EXACTLY before `model --mode ruled` results are trusted.
"""
import sys
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from config import (WEIGHTS, LEGACY_K, LEGACY_QK, REPRO, RULED, WORK)
from model import fit, sig, sig_mom, facet_stats, sigma2_eps, s2eps_mom
from composite import build_boards, eff_shares, norm_simple

W = Path(WORK)

# The ACCEPTED median-k table (owner-accepted; reproduction target).
# cols: dw, eff, medw, sa_med, sa_mean, le0_k (of 18), k_med, k_mean
ACCEPTED = {
    ("RB", "brkTkl_ru"):  (.25, .173, .389, .0171, .0171, 1, 558.8, 560),
    ("RB", "yac_oe_rec"): (.25, .303, .423, .8132, .7260, 3, 87.7, 110),
    ("RB", "explosive"):  (.20, .243, .532, .0104, .0103, 2, 313.5, 319),
    ("RB", "YACcon"):     (.15, .169, .873, .4639, .4624, 0, 51.7, 52),
    ("RB", "brkTkl_rec"): (.10, .043, .301, .0403, .0383, 1, 156.0, 173),
    ("RB", "success"):    (.05, .070, .722, .0375, .0367, 0, 137.2, 143),
    ("WR", "cp"):         (.45, .342, .269, .0205, .0224, 0, 612.7, 516),
    ("WR", "yac_oe"):     (.35, .442, .550, .6975, .6993, 0, 110.6, 110),
    ("WR", "brkTkl_rec"): (.20, .216, .453, .0212, .0211, 0, 172.6, 173),
    ("TE", "yac_oe"):     (.65, .640, .710, .8438, .8645, 0, 60.9, 58),
    ("TE", "brkTkl_rec"): (.35, .360, .502, .0170, .0159, 5, 151.1, 173),
}

QB_GRAIN = {"cpoe": "agg", "bad": "agg", "qsucc": "play", "q10": "play", "deep": "play"}

# The PROTOTYPE (provisional) vectors — the ACCEPTED table's basis. Used ONLY by
# the reproduce/verify parity path; the live board uses config.WEIGHTS (R21).
PROTO_WEIGHTS = {
    "RB": {"brkTkl_ru": .25, "yac_oe_rec": .25, "explosive": .20,
           "YACcon": .15, "brkTkl_rec": .10, "success": .05},
    "WR": {"cp": .45, "yac_oe": .35, "brkTkl_rec": .20},
    "TE": {"yac_oe": .65, "brkTkl_rec": .35},
    "QB": {"cpoe": .35, "bad": .25, "qsucc": .25, "q10": .15, "deep": 0.00},
}


def _load(name):
    with open(W / name, "rb") as fh:
        return pickle.load(fh)


def _save(obj, name):
    with open(W / name, "wb") as fh:
        pickle.dump(obj, fh)


def stage_model(mode_name):
    cfg = REPRO if mode_name == "reproduce" else RULED
    fac = _load("FACETS.pkl")
    # RNG: reproduce mode keeps the prototype's SINGLE SEQUENTIAL stream (byte
    # parity with the accepted table). Ruled modes use PER-FACET child streams
    # keyed [root_seed, position_idx, facet_idx] — root seed 20260716 (R19)
    # retained; isolation means a universe change in one facet can never
    # resample another facet's splits (R20 hardening; flagged for Joseph).
    rng = np.random.default_rng(cfg["SEED"])
    POS_IDX = {"RB": 0, "WR": 1, "TE": 2, "QB": 3}
    F, QU, KD, S2E = {}, {}, {}, {}
    for P in ["RB", "WR", "TE"]:
        F[P] = {}
        for fidx, (nm, df) in enumerate(fac["defs"][P]):
            drop = cfg["DROP_DELTA_BRK"] and nm.startswith("brkTkl")
            d = df.dropna(subset=["y"])
            pu, a, ne = fit(d, drop_delta=drop)
            frng = (rng if mode_name == "reproduce"
                    else np.random.default_rng([cfg["SEED"], POS_IDX[P], fidx]))
            cs = sig(d, frng, cfg["NS"])
            st = facet_stats(cs, floor=cfg["FLOOR"])
            QU[(P, nm)] = st
            if st["unidentifiable"]:
                print(f"UNIDENTIFIABLE (Gate 6 FAIL): {P}/{nm} median sigma^2_alpha "
                      f"= {st['s2a_med']:.6f} <= 0 at NS={cfg['NS']} — EXCLUDED from scoring.")
                continue
            z = a / st["sad"]
            if cfg["K_MODE"] == "legacy":
                k = float(LEGACY_K[P][nm])
            else:
                s2e = sigma2_eps(d, drop_delta=drop)
                S2E[(P, nm)] = s2e
                k = s2e / st["s2a_med"]
            KD[(P, nm)] = k
            F[P][nm] = pd.DataFrame({"a": a, "ne": ne, "z": z,
                                     "w": ne / (ne + k)}, index=pu)
            print(f"  {P}/{nm}: n={len(pu)} sad={st['sad']:.4f} sam={st['sam']:.4f} "
                  f"le0={st['le0']*cfg['NS']:.0f}/{cfg['NS']} k={k:.1f}")
    # ---- QB ----
    F["QB"] = {}
    qc, qrw = fac["qb_career"], fac["qb_rows"]
    if cfg["QB_MODE"] == "legacy":
        for nm in ["cpoe", "bad", "qsucc", "q10"]:
            src = qc[nm]
            w = src.n / (src.n + LEGACY_QK[nm])
            zstd = (src.v - src.v.mean()) / src.v.std()
            F["QB"][nm] = pd.DataFrame({"a": src.v, "ne": src.n,
                                        "z": np.sqrt(w) * zstd, "w": w},
                                       index=src.index)
            KD[("QB", nm)] = float(LEGACY_QK[nm])
    else:
        u5 = None
        for nm in ["cpoe", "bad", "qsucc", "q10", "deep"]:
            u5 = set(qc[nm].index) if u5 is None else (u5 & set(qc[nm].index))
        u5 = sorted(u5)
        print(f"R4 QB universe = complete-case intersection of FIVE facets: n={len(u5)}")
        for qidx, nm in enumerate(["cpoe", "bad", "qsucc", "q10", "deep"]):
            src = qc[nm].loc[u5]
            rows = qrw[nm]; rows = rows[rows.pid.isin(u5)]
            s2e = s2eps_mom(rows, QB_GRAIN[nm])
            qrng = np.random.default_rng([cfg["SEED"], POS_IDX["QB"], qidx])
            cs = sig_mom(rows, qrng, cfg["NS"])
            st = facet_stats(cs, floor=False)
            QU[("QB", nm)] = st
            if st["unidentifiable"]:
                print(f"UNIDENTIFIABLE (Gate 6 FAIL): QB/{nm} — EXCLUDED.")
                continue
            k = s2e / st["s2a_med"]
            S2E[("QB", nm)] = s2e; KD[("QB", nm)] = k
            zstd = (src.v - src.v.mean()) / src.v.std()   # moments on the R4 universe
            F["QB"][nm] = pd.DataFrame({"a": src.v, "ne": src.n, "z": zstd,
                                        "w": src.n / (src.n + k)}, index=src.index)
            print(f"  QB/{nm}: n(U5)={len(src)} sad={st['sad']:.4f} "
                  f"le0={st['le0']*cfg['NS']:.0f}/{cfg['NS']} s2e={s2e:.4f} "
                  f"k={k:.1f} (legacy {LEGACY_QK.get(nm, 'n/a')})")
    _save({"F": F, "QU": QU, "K": KD, "S2E": S2E, "cfg": cfg}, f"MODEL_{mode_name}.pkl")
    print(f"MODEL_{mode_name}.pkl saved")


def _kmed_frames(M):
    """Reproduce-mode helper: rebuild w at the MEDIAN-consistent k
    (k_med = k_legacy*(sam/sad)^2) — the accepted table's basis."""
    F2 = {}
    for P in ["RB", "WR", "TE"]:
        F2[P] = {}
        for nm, fr in M["F"][P].items():
            st = M["QU"][(P, nm)]
            kmed = LEGACY_K[P][nm] * (st["sam"] / st["sad"]) ** 2
            F2[P][nm] = fr.assign(w=fr["ne"] / (fr["ne"] + kmed))
    F2["QB"] = M["F"]["QB"]
    return F2


def stage_board(mode_name):
    M = _load(f"MODEL_{mode_name}.pkl")
    fac = _load("FACETS.pkl")
    F = _kmed_frames(M) if mode_name == "reproduce" else M["F"]
    qb_mode = M["cfg"]["QB_MODE"]
    rz_rb, gname = None, None
    if mode_name != "reproduce":   # ruled path (incl. determinism/alt-seed tags)
        R2 = pickle.load(open("C:/tmp/RHO2.pkl", "rb"))
        rz_rb = R2["RZN"]["RB"]
        sd = fac["sd"]
        gname = dict(zip(sd.player_id, sd.norm_name.fillna(
            sd.player.map(norm_simple))))
    wts = PROTO_WEIGHTS if mode_name == "reproduce" else WEIGHTS
    boards, anchors, audits = build_boards(F, fac["board"], fac["sd"], fac["names"],
                                           qb_mode, rz_rb=rz_rb, gname=gname,
                                           weights=wts)
    if mode_name != "reproduce":
        # every scored QB must sit inside the R4 complete-case universe
        u5 = set(M["F"]["QB"]["cpoe"].index)
        outside = [g for g in boards["QB"].index if g not in u5]
        if outside:
            raise SystemExit(f"R4 VIOLATION: scored QBs outside the complete-case "
                             f"universe: {outside}")
    shares = {P: eff_shares(boards[P], P, weights=wts) for P in boards}
    _save({"boards": boards, "anchors": anchors, "audits": audits,
           "shares": shares}, f"BOARD_{mode_name}.pkl")
    for P in boards:
        print(f"{P}: scored n={len(boards[P])} shares sum="
              f"{sum(shares[P].values()):.6f}")
    if audits.get("RB"):
        print("RB pipe name-collision audit (normalized name -> 2+ gsis):", audits["RB"])
    elif mode_name == "ruled":
        print("RB pipe name-collision audit: NO collisions in scored RB universe")
    print(f"BOARD_{mode_name}.pkl saved")


def _popcov(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return np.mean((x - x.mean()) * (y - y.mean()))


def stage_verify():
    """Regression vs the ACCEPTED table, computed with the accepted table's own
    recipe (median-k w reindexed over the scored board; ddof=0 shares)."""
    M = _load("MODEL_reproduce.pkl"); B = _load("BOARD_reproduce.pkl")
    fails = []
    for P in ["RB", "WR", "TE"]:
        idx = B["boards"][P].index
        facs = list(LEGACY_K[P])
        wm, zz, kmed = {}, {}, {}
        for nm in facs:
            st = M["QU"][(P, nm)]; fr = M["F"][P][nm]
            kmed[nm] = LEGACY_K[P][nm] * (st["sam"] / st["sad"]) ** 2
            ne = fr["ne"].reindex(idx); zz[nm] = fr["z"].reindex(idx).values
            wm[nm] = (ne / (ne + kmed[nm])).values
            miss = int(np.isnan(wm[nm]).sum())
            if miss:
                fails.append(f"{P}/{nm}: {miss} scored players missing this facet "
                             f"(accepted-table recipe assumed zero)")
        c = {nm: wm[nm] * zz[nm] for nm in facs}
        pm = sum(PROTO_WEIGHTS[P][nm] * c[nm] for nm in facs)
        vp = _popcov(pm, pm)
        for nm in facs:
            st = M["QU"][(P, nm)]
            got = dict(sa_med=st["sad"], sa_mean=st["sam"],
                       le0=round(st["le0"] * 18), k_med=kmed[nm],
                       k_mean=LEGACY_K[P][nm],
                       medw=float(np.nanmedian(wm[nm])),
                       eff=PROTO_WEIGHTS[P][nm] * _popcov(c[nm], pm) / vp)
            dw, eff, medw, sa_med, sa_mean, le0k, k_med, k_mean = ACCEPTED[(P, nm)]
            want = dict(sa_med=sa_med, sa_mean=sa_mean, le0=le0k, k_med=k_med,
                        k_mean=k_mean, medw=medw, eff=eff)
            tol = dict(sa_med=6e-5, sa_mean=6e-5, le0=0, k_med=0.06,
                       k_mean=0, medw=6e-4, eff=6e-4)
            for lab in want:
                if abs(got[lab] - want[lab]) > tol[lab]:
                    fails.append(f"{P}/{nm} {lab}: got {got[lab]:.5f} want {want[lab]}")
    if fails:
        print("REPRODUCTION FAILED:"); [print("  " + f) for f in fails]
        sys.exit(1)
    print("REPRODUCTION EXACT: all 11 facets match the accepted table at printed precision.")


def stage_emit():
    """Phase 2: talent_score_2026.csv per the SPEC schema, provenance-stamped."""
    from schemas import validate, write_artifact
    from config import RULED
    M = _load("MODEL_ruled.pkl"); B = _load("BOARD_ruled.pkl")
    FACORD = {"RB": ["brkTkl_ru", "yac_oe_rec", "explosive", "YACcon", "brkTkl_rec",
                     "success"],
              "WR": ["cp", "yac_oe", "brkTkl_rec"], "TE": ["yac_oe", "brkTkl_rec"],
              "QB": ["cpoe", "bad", "deep", "qsucc", "q10"]}
    rows = []
    for P in ["RB", "WR", "TE", "QB"]:
        S = B["boards"][P]
        for g in S.index:
            r = S.loc[g]
            flag = "‡" if r.w < 0.30 else ("†" if r.w < 0.40 else "")
            row = dict(gsis_id=g, display_name=r.nm, position=P,
                       score=round(float(r.score), 1),
                       ci_lo=round(float(max(40, r.score - r.se)), 1),
                       ci_hi=round(float(min(99, r.score + r.se)), 1),
                       w=round(float(r.w), 4), rank_pos=int(r.rank_pos),
                       college_share=round(float(r.college_share), 4), flag=flag)
            for f in FACORD[P]:
                if f + "z" in S.columns:
                    row[f"z_{f}"] = round(float(r[f + "z"]), 4)
                    row[f"w_{f}"] = round(float(r[f + "w"]), 4)
            rows.append(row)
    df = pd.DataFrame(rows)
    validate(df, "talent_score_2026",
             required=["gsis_id", "display_name", "position", "score", "ci_lo",
                       "ci_hi", "w", "rank_pos", "college_share", "flag"],
             no_nan=["gsis_id", "position", "score", "w", "rank_pos"],
             checks={"score in [40,99]": lambda d: d.score.between(40, 99),
                     "unique gsis per pos": lambda d: ~d.duplicated(
                         ["gsis_id", "position"], keep=False)})
    out = Path(__file__).resolve().parent / "talent_score_2026.csv"
    write_artifact(df, out, RULED["NS"], RULED["SEED"],
                   extra={"weights": "PROVISIONAL-UNRATIFIED; QB deepCPOE 0.00 UNSET",
                          "pipe": "RB-only, rho=.385 box-score disattenuated (R10)"})


if __name__ == "__main__":
    stage = sys.argv[1]
    mode = sys.argv[3] if len(sys.argv) > 3 else (sys.argv[2] if len(sys.argv) > 2 else None)
    if stage == "facets":
        from facets import build_inputs; build_inputs()
    elif stage == "model":
        stage_model(mode)
    elif stage == "board":
        stage_board(mode)
    elif stage == "verify":
        stage_verify()
    elif stage == "emit":
        stage_emit()
