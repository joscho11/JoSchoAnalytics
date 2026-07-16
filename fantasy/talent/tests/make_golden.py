"""Freeze golden regression targets from the current ruled checkpoints + artifacts.

SPLIT (2026-07-16): WEIGHT-INDEPENDENT targets (facet-level estimation — sigma
quartets, k, fit-universe n; weights cannot touch these) live in
golden_facets.json; WEIGHT-DEPENDENT targets (eff-shares, rank order, artifact
hashes) live in golden_weighted.json. A weight ratification regenerates ONLY the
weighted file (documented reason required); facet goldens move only on an
instrument change.

Usage: make_golden.py [facets|weighted|all] ["reason"]
"""
import hashlib
import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from config import WORK   # noqa: E402

W = Path(WORK)
GOLD = HERE / "tests" / "golden"
GOLD.mkdir(exist_ok=True)
which = sys.argv[1] if len(sys.argv) > 1 else "all"
reason = sys.argv[2] if len(sys.argv) > 2 else "initial freeze"

M = pickle.load(open(W / "MODEL_ruled.pkl", "rb"))
B = pickle.load(open(W / "BOARD_ruled.pkl", "rb"))

if which in ("facets", "all"):
    g = {"reason": reason, "facets": {}}
    for (P, f), st in M["QU"].items():
        g["facets"][f"{P}/{f}"] = {k: float(st[k]) for k in
                                   ["sad", "sam", "cs_std", "cv", "le0"]}
        g["facets"][f"{P}/{f}"]["k"] = float(M["K"][(P, f)])
        g["facets"][f"{P}/{f}"]["n_fit"] = int(len(M["F"][P][f]))
    (GOLD / "golden_facets.json").write_text(json.dumps(g, indent=1))
    print(f"golden_facets.json frozen ({len(g['facets'])} facets) reason: {reason}")

if which in ("weighted", "all"):
    g = {"reason": reason, "rank_order": {}, "eff_shares": {}, "artifact_md5": {}}
    for P, S in B["boards"].items():
        g["rank_order"][P] = list(S.index)
        g["eff_shares"][P] = {f: float(v) for f, v in B["shares"][P].items()}
    for n in ["talent_score_2026.csv", "rookie_score_2026.csv"]:
        p = HERE / n
        if p.exists():
            g["artifact_md5"][n] = hashlib.md5(p.read_bytes()).hexdigest()
    (GOLD / "golden_weighted.json").write_text(json.dumps(g, indent=1))
    print(f"golden_weighted.json frozen "
          f"({sum(len(v) for v in g['rank_order'].values())} ranked players, "
          f"{len(g['artifact_md5'])} artifact hashes) reason: {reason}")
