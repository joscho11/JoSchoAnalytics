"""SYNTHETIC pre-build INPUT fixture: a miniature FACETS.pkl.

Why this exists
---------------
`tests/fixtures/work/` holds committed OUTPUT checkpoints (MODEL_*.pkl,
BOARD_*.pkl). Those prove the committed bytes are stable; they prove NOTHING
about whether running today's builder code still produces them. This module
closes that gap from the other end: it manufactures a small, fully synthetic
*input* checkpoint that the REAL build stages
(`build_talent_score.stage_model` / `stage_board`, which call `model.fit`,
`model.sig`, `model.sigma2_eps`, `model.sig_mom`, `model.s2eps_mom`,
`composite.build_boards`, `composite.eff_shares`, `schemas.stable_rank_sort`)
can actually be driven with, twice, in two scratch dirs.

Licensing
---------
Every number here is drawn from `numpy.random.default_rng(SEED)`. No PFF row,
no nflverse row, no real player id and no real player name is present or
derivable. The ids are `SYN-<POS>-<n>` and the names are `Synth <Pos> <n>`.
It is therefore freely committable, unlike the licensed real inputs.

Determinism
-----------
The generator is itself part of what must be deterministic, so
`digest_facets()` gives a canonical, ordering-insensitive fingerprint of the
produced structure, pinned by `test_build_determinism.py`.
"""
import hashlib
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260803

SEASONS = (2022, 2023, 2024, 2025)
WEEKS = 8
TEAMS = ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH")
LAM = 0.20   # mirrors config.LAM; the fixture is an INPUT, so it bakes w itself

# facet order per position MUST match facets.build_inputs()'s `defs` order --
# reproduce-mode RNG parity is order-dependent (see build_talent_score).
FACET_ORDER = {
    "RB": ["YACcon", "brkTkl_ru", "success", "explosive", "yac_oe_rec", "brkTkl_rec"],
    "WR": ["yac_oe", "cp", "brkTkl_rec"],
    "TE": ["yac_oe", "brkTkl_rec"],
}
N_PLAYERS = {"RB": 45, "WR": 45, "TE": 30, "QB": 26}
QB_FACETS = ("cpoe", "bad", "qsucc", "q10", "deep")


def _pid(pos, i):
    return f"SYN-{pos}-{i:04d}"


def _facet_frame(rng, pids, sigma_alpha, sigma_eps, opp_lo, opp_hi):
    """A week-grain facet frame with a genuine crossed structure:
    y = alpha_player + gamma_teamseason + delta_opponentseason + noise/sqrt(o).
    Columns match facets.build_inputs(): pid, season, ts, os, y, w, o."""
    alpha = dict(zip(pids, rng.normal(0, sigma_alpha, len(pids))))
    gamma = {f"{t}_{s}": g for (t, s), g in zip(
        [(t, s) for t in TEAMS for s in SEASONS],
        rng.normal(0, 0.4 * sigma_alpha, len(TEAMS) * len(SEASONS)))}
    delta = {f"{t}_{s}": g for (t, s), g in zip(
        [(t, s) for t in TEAMS for s in SEASONS],
        rng.normal(0, 0.3 * sigma_alpha, len(TEAMS) * len(SEASONS)))}
    rows = []
    for p_i, p in enumerate(pids):
        team = TEAMS[p_i % len(TEAMS)]
        for s in SEASONS:
            for wk in range(1, WEEKS + 1):
                opp = TEAMS[(p_i + wk) % len(TEAMS)]
                o = int(rng.integers(opp_lo, opp_hi + 1))
                ts, os_ = f"{team}_{s}", f"{opp}_{s}"
                y = (alpha[p] + gamma[ts] + delta[os_]
                     + rng.normal(0, sigma_eps) / np.sqrt(o))
                rows.append((p, s, ts, os_, y,
                             o * float(np.exp(-LAM * (2025 - s))), o))
    return pd.DataFrame(rows, columns=["pid", "season", "ts", "os", "y", "w", "o"])


def _qb_feeds(rng, pids):
    """qb_career: index=pid, cols v,n. qb_rows: per-facet row-level feeds.
    `cpoe`/`bad` are QB_GRAIN 'agg' (need an `att` column and >=2 rows/pid);
    `qsucc`/`q10`/`deep` are 'play' grain."""
    career, rows = {}, {}
    scales = {"cpoe": (2.5, 4.0, 480.0), "bad": (2.0, 3.5, 430.0),
              "qsucc": (0.06, 0.30, 46.0), "q10": (0.05, 0.28, 46.0),
              "deep": (2.0, 6.0, 34.0)}
    for nm in QB_FACETS:
        sa, se, nscale = scales[nm]
        alpha = dict(zip(pids, rng.normal(0, sa, len(pids))))
        if nm in ("cpoe", "bad"):
            rr = []
            for p in pids:
                for s in SEASONS:
                    att = float(rng.integers(120, 420))
                    v = alpha[p] + rng.normal(0, se) / np.sqrt(att)
                    rr.append((p, v, att, att * float(np.exp(-LAM * (2025 - s)))))
            fr = pd.DataFrame(rr, columns=["pid", "v", "att", "wgt"])
            rows[nm] = fr
            g = fr.groupby("pid")[["v", "wgt"]].apply(
                lambda x: pd.Series({"v": np.sum(x.v * x.wgt) / np.sum(x.wgt),
                                     "n": np.sum(x.wgt)}))
        else:
            rr = []
            for p in pids:
                for s in SEASONS:
                    for _ in range(int(rng.integers(14, 26))):
                        v = alpha[p] + rng.normal(0, se)
                        rr.append((p, v, float(np.exp(-LAM * (2025 - s)))))
            fr = pd.DataFrame(rr, columns=["pid", "v", "wgt"])
            rows[nm] = fr
            g = fr.groupby("pid")[["v", "wgt"]].apply(
                lambda x: pd.Series({"v": np.sum(x.v * x.wgt) / np.sum(x.wgt),
                                     "n": np.sum(x.wgt)}))
        # rescale n to a realistic career-opportunity magnitude (drives w=n/(n+k))
        g["n"] = g["n"] * (nscale / g["n"].mean())
        career[nm] = g
    return career, rows


def build_synth_facets(seed: int = SEED) -> dict:
    """Return a FACETS.pkl-shaped dict of purely synthetic data."""
    rng = np.random.default_rng(seed)
    pids = {P: [_pid(P, i) for i in range(N_PLAYERS[P])] for P in N_PLAYERS}

    # (sigma_alpha, sigma_eps, opp_lo, opp_hi) per facet
    spec = {
        ("RB", "YACcon"): (0.55, 1.6, 8, 22),
        ("RB", "brkTkl_ru"): (0.030, 0.28, 8, 22),
        ("RB", "success"): (0.045, 0.42, 8, 22),
        ("RB", "explosive"): (0.028, 0.30, 8, 22),
        ("RB", "yac_oe_rec"): (0.90, 2.4, 3, 9),
        ("RB", "brkTkl_rec"): (0.060, 0.55, 3, 9),
        ("WR", "yac_oe"): (0.85, 2.2, 4, 12),
        ("WR", "cp"): (0.045, 0.40, 5, 14),
        ("WR", "brkTkl_rec"): (0.055, 0.50, 4, 12),
        ("TE", "yac_oe"): (0.95, 2.3, 3, 10),
        ("TE", "brkTkl_rec"): (0.058, 0.52, 3, 10),
    }
    defs = {P: [(nm, _facet_frame(rng, pids[P], *spec[(P, nm)]))
                for nm in FACET_ORDER[P]]
            for P in FACET_ORDER}

    qb_career, qb_rows = _qb_feeds(rng, pids["QB"])

    all_pids, all_pos = [], []
    for P in ("RB", "WR", "TE", "QB"):
        all_pids += pids[P]
        all_pos += [P] * len(pids[P])
    names = {p: f"Synth {p.split('-')[1].title()} {p.split('-')[2]}"
             for p in all_pids}
    board = pd.DataFrame({"player_id": all_pids, "position": all_pos})
    sd = pd.DataFrame({"player_id": all_pids,
                       "player": [names[p] for p in all_pids],
                       "norm_name": [names[p].lower() for p in all_pids],
                       "position": all_pos,
                       "adp_overall_rank": np.arange(1, len(all_pids) + 1),
                       "season": 2026})
    return {"defs": defs, "names": names, "p2g": {}, "board": board, "sd": sd,
            "nfl_ids": set(all_pids),
            "qb_career": qb_career, "qb_rows": qb_rows,
            "_synthetic": True}


def shuffle_row_order(fac: dict, shuffle_seed: int) -> dict:
    """MUTATION HOOK (used only by the red proof).

    Permutes the ROW ORDER of every facet frame and every QB row-level feed.
    The multiset of rows -- every value, every dtype -- is preserved exactly;
    only the order in which the builder receives them changes. This is the
    canonical latent nondeterminism of this pipeline: `model.sig` /
    `model.sig_mom` assign split halves with `rng.random(len(d)) < 0.5`, which
    is positional, so an upstream ordering wobble (a set iteration, an unstable
    groupby/dedupe, a differently-ordered source pull) silently moves every
    sigma^2_alpha, every derived k, and every shrinkage weight.
    """
    rng = np.random.default_rng(shuffle_seed)

    def perm(df):
        return df.iloc[rng.permutation(len(df))].reset_index(drop=True)

    out = dict(fac)
    out["defs"] = {P: [(nm, perm(df)) for nm, df in fac["defs"][P]]
                   for P in fac["defs"]}
    out["qb_rows"] = {nm: perm(df) for nm, df in fac["qb_rows"].items()}
    out["_row_shuffled"] = shuffle_seed
    return out


def write_synth_facets(work_dir, seed: int = SEED,
                       shuffle_seed: int = None) -> Path:
    """Write FACETS.pkl into `work_dir` (created if absent). Returns the path.

    `shuffle_seed` is the mutation hook -- leave it None for the real fixture.
    """
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    fac = build_synth_facets(seed)
    if shuffle_seed is not None:
        fac = shuffle_row_order(fac, shuffle_seed)
    out = work / "FACETS.pkl"
    with open(out, "wb") as fh:
        pickle.dump(fac, fh, protocol=4)
    return out


# ---- canonical, ordering-insensitive fingerprint -------------------------------

def _frame_digest(df: pd.DataFrame) -> str:
    """Canonical digest of a frame: index folded in, columns sorted, rows sorted,
    floats at fixed precision. Insensitive to row/column ORDER, sensitive to
    values, dtypes and shape."""
    d = df.copy()
    d.insert(0, "__index__", [str(i) for i in d.index])
    d = d.reindex(sorted(d.columns), axis=1)
    dtypes = "|".join(f"{c}:{d[c].dtype}" for c in d.columns)
    d = d.sort_values(list(d.columns), kind="mergesort").reset_index(drop=True)
    body = d.to_csv(index=False, float_format="%.12g", lineterminator="\n")
    return hashlib.sha256((dtypes + "\n" + body).encode()).hexdigest()


def digest_facets(fac: dict) -> str:
    parts = []
    for P in sorted(fac["defs"]):
        for nm, df in fac["defs"][P]:          # order-SENSITIVE on purpose
            parts.append(f"defs/{P}/{nm}={_frame_digest(df)}")
    for nm in sorted(fac["qb_career"]):
        parts.append(f"qbc/{nm}={_frame_digest(pd.DataFrame(fac['qb_career'][nm]))}")
    for nm in sorted(fac["qb_rows"]):
        parts.append(f"qbr/{nm}={_frame_digest(fac['qb_rows'][nm])}")
    parts.append(f"board={_frame_digest(fac['board'])}")
    parts.append(f"sd={_frame_digest(fac['sd'])}")
    parts.append("nfl_ids=" + hashlib.sha256(
        "|".join(sorted(fac["nfl_ids"])).encode()).hexdigest())
    parts.append("names=" + hashlib.sha256(
        "|".join(f"{k}={fac['names'][k]}" for k in sorted(fac["names"])).encode()
    ).hexdigest())
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


if __name__ == "__main__":
    import sys
    fac = build_synth_facets()
    print("digest:", digest_facets(fac))
    print({P: [(nm, len(df)) for nm, df in fac["defs"][P]] for P in fac["defs"]})
    print({k: len(v) for k, v in fac["qb_rows"].items()})
    if len(sys.argv) > 1:
        print("wrote", write_synth_facets(sys.argv[1]))
