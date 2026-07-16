"""R9 — archival reproduction of the registered PBP-rho outputs.

The prototype cfb_rho.py registered FOUR estimators (raw Pearson, w-weighted
Pearson, disattenuated Pearson, Spearman; per-position + pooled) but printed only
three and saved nothing. This script (1) verifies the frozen inputs byte-match
their snapshot pins, (2) executes cfb_rho.py UNMODIFIED and captures stdout,
(3) recomputes all four estimators deterministically from the same frozen pickles
(no RNG touches any point estimate), (4) verifies the recomputation against the
captured stdout AND against the values relayed in the session record, and
(5) persists everything to rho_provenance.json alongside the box-score test #2
values from RHO2.res. This is archival of registered outputs, not a re-run.
"""
import hashlib
import json
import re
import subprocess
import sys
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

HERE = Path(__file__).resolve().parent
SEASONAL = HERE.parent / "seasonal_projections"
SCRATCH = Path(r"C:\Users\josep\AppData\Local\Temp\claude"
               r"\c--Users-josep-Desktop-random-stuff-cowork-OS"
               r"\05f61ef9-5fea-4c1a-918e-96d84f266591\scratchpad")
PINS = {
    SCRATCH / "cfb_rho.py": "e80badc1006f4b29ab74d67c8d40511b",
    Path("C:/tmp/S2.pkl"): "9b3d9df67ae88272f4eab0a0ae1cbb21",
    Path("C:/tmp/CFBFAC.pkl"): "58e5fe3768430bed9406c5cacfeafa54",
    Path("C:/tmp/RHO2.pkl"): "886b4249e35ffecbd221c94d6f5fb660",
}
RELAYED = {  # what prior reports relayed (disatt / w-wt / n)
    "RB": (0.407, 0.126, 323), "WR": (0.376, 0.321, 331),
    "TE": (0.288, 0.095, 123), "pooled": (0.371, 0.164, 777),
}

for p, pin in PINS.items():
    got = hashlib.md5(p.read_bytes()).hexdigest()
    print(f"{p.name}  {got}  (pin {pin})  {'OK' if got == pin else '** MISMATCH — STOP **'}")
    if got != pin:
        sys.exit("ARCHIVAL ABORTED: input differs from snapshot pin.")

# ---- (b) byte-identical execution --------------------------------------------
r = subprocess.run([sys.executable, str(SCRATCH / "cfb_rho.py")],
                   cwd=str(SEASONAL), capture_output=True, text=True, timeout=1200)
stdout = r.stdout
print("--- captured cfb_rho.py stdout ---")
print(stdout)
if r.returncode != 0:
    print(r.stderr); sys.exit("cfb_rho.py failed")

printed = {}
for m in re.finditer(r"^\s+(RB|WR|TE) n=(\d+) mean-w=([\d.]+) \| raw=(-?[\d.]+)\(.*?"
                     r"w-wt=(-?[\d.]+)\(.*?disatt=(-?[\d.]+)", stdout, re.M):
    printed[m.group(1)] = dict(n=int(m.group(2)), raw=float(m.group(4)),
                               wwt=float(m.group(5)), disatt=float(m.group(6)))
m = re.search(r"POOLED n=(\d+) \| raw=(-?[\d.]+) w-wt=(-?[\d.]+) disatt=(-?[\d.]+)", stdout)
printed["pooled"] = dict(n=int(m.group(1)), raw=float(m.group(2)),
                         wwt=float(m.group(3)), disatt=float(m.group(4)))

# ---- (c) deterministic recomputation incl. Spearman (verbatim data prep) -----
sys.path.insert(0, str(SEASONAL))
from _utils import norm_name  # noqa: E402

S = pickle.load(open("C:/tmp/S2.pkl", "rb"))
F, QU, W, names = S["F"], S["QU"], S["W"], S["names"]
CF = pickle.load(open("C:/tmp/CFBFAC.pkl", "rb")); CAREER = CF["CAREER"]
kold = {"RB": {"brkTkl_ru": 560, "yac_oe_rec": 110, "explosive": 319, "YACcon": 52,
               "brkTkl_rec": 173, "success": 143},
        "WR": {"cp": 516, "yac_oe": 110, "brkTkl_rec": 173},
        "TE": {"yac_oe": 58, "brkTkl_rec": 173}}
knew = {P: {f: kold[P][f] * (QU[(P, f)]["sam"] / QU[(P, f)]["sad"]) ** 2
            for f in kold[P]} for P in kold}


def nn(x):
    return norm_name(str(x))


def alpha_w(P):
    facs = list(W[P]); idx = set().union(*[set(F[P][f].index) for f in facs])
    D = pd.DataFrame(index=list(idx))
    aw = pd.Series(0.0, index=D.index); wt = pd.Series(0.0, index=D.index)
    for f in facs:
        ne = F[P][f]["ne"].reindex(D.index).fillna(0)
        wn = ne / (ne + knew[P][f])
        z = F[P][f]["zmed"].reindex(D.index).fillna(0)
        aw = aw + W[P][f] * z; wt = wt + W[P][f] * wn
    return aw, wt / sum(W[P].values())


SEL = {"RB": ["EPA/rush", "explosive"], "REC": ["EPA/tgt", "catch%", "explosive_rec"]}


def zpool(facdict, sel):
    df = pd.DataFrame({s: facdict[s] for s in sel}).dropna()
    for s in sel:
        df[s] = (df[s] - df[s].mean()) / df[s].std()
    return df.mean(axis=1)


RZ = {"RB": {nn(k): v for k, v in zpool(CAREER["RB"], SEL["RB"]).items()},
      "REC": {nn(k): v for k, v in zpool(CAREER["WR"], SEL["REC"]).items()}}


def wpear(x, y, w):
    mx = np.average(x, weights=w); my = np.average(y, weights=w)
    cov = np.average((x - mx) * (y - my), weights=w)
    return cov / np.sqrt(np.average((x - mx) ** 2, weights=w)
                         * np.average((y - my) ** 2, weights=w))


recomp, POOL = {}, []
for P in ["RB", "WR", "TE"]:
    aw, wt = alpha_w(P)
    src = RZ["RB"] if P == "RB" else RZ["REC"]
    rz = pd.Series({p: src.get(nn(names.get(p, "")), np.nan) for p in aw.index})
    m = (wt > 0) & rz.notna() & aw.notna()
    x = rz[m].values; y = aw[m].values; wv = wt[m].values
    recomp[P] = dict(n=int(m.sum()),
                     raw=float(pearsonr(x, y)[0]),
                     spearman=float(spearmanr(x, y).correlation),
                     wwt=float(wpear(x, y, wv)),
                     disatt=float(pearsonr(x, y)[0] / np.sqrt(wv.mean())))
    POOL.append(pd.DataFrame({"x": (x - x.mean()) / x.std(),
                              "y": (y - y.mean()) / y.std(), "w": wv}))
PP = pd.concat(POOL)
recomp["pooled"] = dict(
    n=len(PP), raw=float(pearsonr(PP.x, PP.y)[0]),
    spearman=float(spearmanr(PP.x, PP.y).correlation),
    wwt=float(wpear(PP.x.values, PP.y.values, PP.w.values)),
    disatt=float(pearsonr(PP.x, PP.y)[0] / np.sqrt(PP.w.mean())))

# ---- (d) verification: recomputation vs printed vs relayed -------------------
alerts = []
for k in printed:
    for est in ("raw", "wwt", "disatt"):
        if abs(round(recomp[k][est], 3) - printed[k][est]) > 5e-4:
            alerts.append(f"{k}/{est}: recomputed {recomp[k][est]:.3f} != printed {printed[k][est]:.3f}")
    if recomp[k]["n"] != printed[k]["n"]:
        alerts.append(f"{k}/n: {recomp[k]['n']} != printed {printed[k]['n']}")
for k, (dis, ww, n) in RELAYED.items():
    if abs(round(recomp[k]["disatt"], 3) - dis) > 5e-4:
        alerts.append(f"RED ALERT {k}/disatt: {recomp[k]['disatt']:.3f} != relayed {dis}")
    if abs(round(recomp[k]["wwt"], 3) - ww) > 5e-4:
        alerts.append(f"RED ALERT {k}/w-wt: {recomp[k]['wwt']:.3f} != relayed {ww}")
    if recomp[k]["n"] != n:
        alerts.append(f"RED ALERT {k}/n: {recomp[k]['n']} != relayed {n}")

R2 = pickle.load(open("C:/tmp/RHO2.pkl", "rb"))
box = {P: {kk: (float(v) if isinstance(v, (int, float, np.floating)) else None)
           for kk, v in R2["res"][P].items() if kk in ("n", "meanw", "rp", "rs", "rw", "rc")}
       for P in R2["res"]}

prov = {
    "written": "2026-07-16", "protocol": "R9 archival (one sanctioned execution)",
    "pbp_rho": {
        "preregistration_verbatim": [
            "PRE-REG: rho=corr(R_z_new,alpha-hat), all JOIN-B w>0, disattenuated by "
            "sqrt(mean w); raw+w-weighted+Spearman; per-pos+pooled.",
            "Committed: rho_new>=.50 pipe ships / .35-.50 weak / <.35 dead. "
            "Box-score baseline: RB .385 WR .000 TE .254."],
        "target": "UNSHRUNK composite sum(W_f*z_f) (alpha-hat), median-k w for the sample filter",
        "bands_carried_by": "disattenuated estimator (R8, committed before Spearman seen)",
        "coverage_caveat": "PBP college index covers 2016/18/19/21/22 final seasons only",
        "estimators": recomp,
        "printed_by_byte_identical_run": printed,
        "note_spearman": "Spearman was registered and computed by the prototype but never "
                         "printed or saved; recovered here deterministically (no RNG in any "
                         "point estimate). Pooled Spearman was registered and never computed "
                         "by the prototype; computed here on the same pooled frame.",
        "verification_alerts": alerts,
        "stdout_verbatim": stdout,
    },
    "box_score_test2": {
        "target": "UNSHRUNK composite sum(W_f*z_f), all JOIN-B w>0 (step2.py)",
        "estimator_map": {"rp": "raw Pearson", "rs": "Spearman",
                          "rw": "w-weighted Pearson", "rc": "disattenuated"},
        "values": box,
        "pooled_rc": float(R2["pooled_rc"]), "pooled_rw": float(R2["pooled_rw"]),
    },
}
(HERE / "rho_provenance.json").write_text(json.dumps(prov, indent=1))
print("\n=== RECOMPUTED (all four registered estimators) ===")
for k in ("RB", "WR", "TE", "pooled"):
    v = recomp[k]
    print(f"  {k:6s} n={v['n']:4d} raw={v['raw']:+.3f} w-wt={v['wwt']:+.3f} "
          f"disatt={v['disatt']:+.3f} spearman={v['spearman']:+.3f}")
print("ALERTS:" if alerts else "VERIFIED: recomputation matches printed and relayed values exactly.")
for a in alerts:
    print("  " + a)
print("rho_provenance.json written")
