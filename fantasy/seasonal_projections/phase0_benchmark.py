"""PHASE 0 — season-long benchmark ladder + ranking/value eval harness.

Seasonal drafting is a RANKING and VALUE problem, so this harness grades every
projection source on decision-relevant metrics, by position, walk-forward:

  Ladder (weakest -> strongest prior):
    naive_pts   : prior-season total half-PPR points
    naive_ppg17 : prior-season PPG x 17
    age_curve   : prior PPG x position age-multiplier x 17 (multipliers fit only
                  on seasons < t -- no hindsight)
    model_wf    : our Model A config (per-position LightGBM, injury feats removed),
                  RETRAINED walk-forward on seasons < t, PPG_pred x 17
    adp         : market consensus (Sleeper ADP 2020+, FFC ADP 2014-2019)
    ecr         : FantasyPros preseason draft ECR via nflreadpy load_ff_rankings
                  (exists 2020+ only; last scrape on/before Aug 31, ecr_type 'do')
    sleeper     : Sleeper's own preseason season-point projection (cached 2020+)

  Metrics within position, averaged over eval seasons:
    rho      : Spearman(source rank, actual season points) on the drafted pool
    top12/24 : of the source's preseason top-N at the position, share that
               finished top-N in actual points
    bust     : of the source's preseason top-24 (RB/WR) / top-12 (QB/TE), share
               that finished outside top-36 / top-18 among ALL actives
    vor_mae  : MAE of predicted vs actual value-over-replacement
               (replacement = QB14/RB30/WR36/TE14) -- point sources only
    mae      : season-point MAE on matched rows -- point sources only

  Pool: ADP top-180 overall per season (the draftable universe). Sources that
  cannot see a player (e.g. naive baselines on rookies) rank them last -- that
  is their honest performance, not an artifact. A veterans-only slice is also
  reported so the rookie penalty is visible.

Eval panels: 2020-2025 (all rungs) and 2016-2019 (FFC ADP era; no ECR/Sleeper).
Actual season points are recomputed from load_player_stats, independent of the
dataset build. Output: printed tables + phase0_benchmark_results.json.

Run:  python fantasy/seasonal_projections/phase0_benchmark.py
"""
import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from lightgbm import LGBMRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _utils import norm_name, SKILL_POSITIONS

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE      = Path(__file__).resolve().parent
DATA      = HERE / "season_dataset_2014_2025.csv"
FFC_CSV   = HERE / "ffc_adp_2014_2019.csv"
ECR_CSV   = HERE / "ecr_preseason.csv"
OUT_JSON  = HERE / "phase0_benchmark_results.json"

POSITIONS   = ["QB", "RB", "WR", "TE"]
POOL_SIZE   = 180                       # ADP top-180 = the draftable universe
REPLACEMENT = {"QB": 14, "RB": 30, "WR": 36, "TE": 14}
BUST_DRAFT  = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}   # "drafted top-N"
BUST_FINISH = {"QB": 18, "RB": 36, "WR": 36, "TE": 18}   # "finished outside top-N"
AGE_BUCKETS = [(0, 23.5), (23.5, 25.5), (25.5, 27.5), (27.5, 29.5), (29.5, 32.5), (32.5, 99)]

PANELS = {"2020-2025 (all sources)": list(range(2020, 2026)),
          "2016-2019 (FFC ADP era)": list(range(2016, 2020))}

# exact shipped Model A config (train_model_a.py) -- retrained walk-forward here
EXCLUDE = {
    "player_id", "player", "norm_name", "team", "position", "season", "reconstructed",
    "target_ppg", "target_games", "sample_weight",
    "adp_half_ppr", "adp_overall_rank", "adp_pos_rank", "sleeper_pts_half_ppr",
    "prior_games_missed", "missed_prior_season",
}
LGBM_PARAMS = dict(objective="mae", num_leaves=20, learning_rate=0.03, n_estimators=600,
                   min_child_samples=25, reg_lambda=3.0, subsample=0.8, subsample_freq=1,
                   random_state=42, n_jobs=-1, verbose=-1)


# ── data assembly ─────────────────────────────────────────────────────────────
def load_actual_points():
    """Actual season half-PPR totals, recomputed independently of the dataset."""
    import nflreadpy as nfl
    ps = nfl.load_player_stats(list(range(2014, 2026))).to_pandas()
    ps = ps[(ps["season_type"] == "REG") & (ps["position"].isin(SKILL_POSITIONS))].copy()
    ps["half_ppr"] = ps["fantasy_points"].fillna(0) + 0.5 * ps["receptions"].fillna(0)
    act = ps.groupby(["player_id", "season"])["half_ppr"].sum().rename("actual_pts").reset_index()
    return act


def build_ecr_cache():
    """Preseason FantasyPros draft-overall ECR per season (last scrape <= Aug 31)."""
    import nflreadpy as nfl
    fr = nfl.load_ff_rankings("all").to_pandas()
    fr = fr[(fr["ecr_type"] == "do") & fr["pos"].isin(SKILL_POSITIONS)].copy()
    fr["scrape_date"] = pd.to_datetime(fr["scrape_date"], errors="coerce")
    fr["season"] = fr["scrape_date"].dt.year
    fr = fr[fr["scrape_date"].dt.month <= 8]
    last = fr.groupby("season")["scrape_date"].max().rename("last_scrape")
    fr = fr.merge(last, on="season")
    fr = fr[fr["scrape_date"] == fr["last_scrape"]]
    fr["norm_name"] = fr["player"].map(norm_name)
    out = (fr[["season", "norm_name", "pos", "ecr"]]
           .rename(columns={"pos": "position"})
           .dropna(subset=["ecr"])
           .drop_duplicates(["season", "norm_name", "position"]))
    out.to_csv(ECR_CSV, index=False)
    print(f"  cached preseason ECR: {len(out):,} rows, seasons "
          f"{out.season.min()}-{out.season.max()}")
    return out


def assemble():
    df = pd.read_csv(DATA)
    df = df[df["reconstructed"] == 0].copy()

    act = load_actual_points()
    df = df.merge(act, on=["player_id", "season"], how="left")
    df["actual_pts"] = df["actual_pts"].fillna(0.0)

    # unified ADP: Sleeper (2020+) else FFC (2014-2019)
    df["adp"] = df["adp_half_ppr"]
    if FFC_CSV.exists():
        ffc = pd.read_csv(FFC_CSV)[["season", "norm_name", "position", "ffc_adp"]]
        df = df.merge(ffc, on=["season", "norm_name", "position"], how="left")
        df["adp"] = df["adp"].fillna(df["ffc_adp"])

    ecr = pd.read_csv(ECR_CSV) if ECR_CSV.exists() else build_ecr_cache()
    df = df.merge(ecr, on=["season", "norm_name", "position"], how="left")
    return df


def walk_forward_model(df):
    """Model A config retrained on seasons < t; returns ppg predictions per row."""
    harness_cols = {"actual_pts", "adp", "ffc_adp", "ecr", "naive_pts", "naive_ppg17",
                    "age_curve", "model_wf", "finish_all", "adp_overall"}
    feats = [c for c in df.columns if c not in EXCLUDE and c not in harness_cols]
    preds = pd.Series(np.nan, index=df.index)
    eval_seasons = sorted({s for panel in PANELS.values() for s in panel})
    for t in eval_seasons:
        train = df[(df.season < t) & df.target_ppg.notna()]
        test_idx = df.index[df.season == t]
        if len(train) < 200 or not len(test_idx):
            continue
        for pos in POSITIONS:
            tr = train[train.position == pos]
            te = df.loc[test_idx][df.loc[test_idx, "position"] == pos]
            if len(tr) < 50 or not len(te):
                continue
            m = LGBMRegressor(**LGBM_PARAMS)
            m.fit(tr[feats], tr.target_ppg, sample_weight=tr.sample_weight)
            preds.loc[te.index] = m.predict(te[feats])
    return preds


def age_curve_pred(df):
    """prior PPG x age multiplier x 17, multipliers fit on seasons < t only."""
    hist = df[df.prior_ppg.notna() & df.target_ppg.notna()].copy()
    out = pd.Series(np.nan, index=df.index)
    for t in sorted(df.season.unique()):
        train = hist[hist.season < t]
        rows = df[(df.season == t) & df.prior_ppg.notna() & df.age.notna()]
        if len(train) < 300 or not len(rows):
            continue
        mult = {}
        for pos in POSITIONS:
            tp = train[train.position == pos]
            for lo, hi in AGE_BUCKETS:
                b = tp[(tp.age >= lo) & (tp.age < hi) & (tp.prior_ppg > 1)]
                ratio = (b.target_ppg / b.prior_ppg).clip(0.2, 3.0)
                mult[(pos, lo)] = float(ratio.median()) if len(b) >= 20 else 1.0
        for i, r in rows.iterrows():
            lo = next(lo for lo, hi in AGE_BUCKETS if lo <= r.age < hi)
            out.loc[i] = r.prior_ppg * mult[(r.position, lo)] * 17
    return out


# ── metrics ───────────────────────────────────────────────────────────────────
def finish_ranks(df):
    """Actual finish rank among ALL active players at the position (per season)."""
    return df.groupby(["season", "position"])["actual_pts"].rank(ascending=False, method="min")


def eval_source(pool, score_col, ascending, positions=POSITIONS):
    """Grade one source on the drafted pool. score_col NaN -> ranked last."""
    res = {}
    for pos in positions:
        rows_all = []
        for season, grp in pool[pool.position == pos].groupby("season"):
            g = grp.copy()
            if g[score_col].notna().sum() < 5:
                continue
            g["src_rank"] = g[score_col].rank(ascending=ascending, na_option="bottom", method="first")
            g["act_rank"] = g["actual_pts"].rank(ascending=False, method="first")
            rows_all.append(g)
        if not rows_all:
            continue
        g = pd.concat(rows_all)
        seasons = g.season.unique()

        rhos, hit12, hit24, busts, n_bust = [], [], [], 0, 0
        for season, s in g.groupby("season"):
            rhos.append(spearmanr(s.src_rank, s.actual_pts).statistic * -1)
            top12 = s[s.src_rank <= 12]
            top24 = s[s.src_rank <= 24]
            hit12.append((top12.act_rank <= 12).mean() if len(top12) >= 12 else np.nan)
            hit24.append((top24.act_rank <= 24).mean() if len(top24) >= 24 else np.nan)
            drafted = s[s.src_rank <= BUST_DRAFT[pos]]
            busts += (drafted.finish_all > BUST_FINISH[pos]).sum()
            n_bust += len(drafted)
        res[pos] = {
            "rho": float(np.nanmean(rhos)),
            "top12_hit": float(np.nanmean(hit12)),
            "top24_hit": float(np.nanmean(hit24)),
            "bust_rate": busts / n_bust if n_bust else np.nan,
            "n": int(len(g)), "seasons": int(len(seasons)),
            "coverage": float(g[score_col].notna().mean()),
        }
        # point-scale metrics on matched rows only
        m = g[g[score_col].notna()]
        if ascending is False:      # higher score = better = a point projection
            res[pos]["mae"] = float((m[score_col] - m.actual_pts).abs().mean())
            res[pos]["rmse"] = float(np.sqrt(((m[score_col] - m.actual_pts) ** 2).mean()))
            vor_p, vor_a = [], []
            for season, s in m.groupby("season"):
                if len(s) < REPLACEMENT[pos]:
                    continue
                rp = s[score_col].nlargest(REPLACEMENT[pos]).iloc[-1]
                ra = s["actual_pts"].nlargest(REPLACEMENT[pos]).iloc[-1]
                vor_p.append(s[score_col] - rp); vor_a.append(s["actual_pts"] - ra)
            if vor_p:
                vp, va = pd.concat(vor_p), pd.concat(vor_a)
                res[pos]["vor_mae"] = float((vp - va).abs().mean())
    return res


def print_panel(results, title):
    print(f"\n{'='*100}\nPANEL: {title}\n{'='*100}")
    for pos in POSITIONS:
        print(f"\n  {pos}  (rho / top12 / top24 / bust / vor_mae / mae / coverage)")
        print(f"  {'source':12} {'rho':>6} {'top12':>6} {'top24':>6} {'bust':>6} "
              f"{'vorMAE':>7} {'MAE':>6} {'cov':>5} {'n':>5}")
        for src, by_pos in results.items():
            r = by_pos.get(pos)
            if not r:
                continue
            fmt = lambda k, w=6, p=3: f"{r[k]:>{w}.{p}f}" if k in r and pd.notna(r[k]) else " " * (w - 3) + "  -"
            print(f"  {src:12} {fmt('rho')} {fmt('top12_hit')} {fmt('top24_hit')} "
                  f"{fmt('bust_rate')} {fmt('vor_mae',7,1)} {fmt('mae',6,1)} "
                  f"{r['coverage']:>5.0%} {r['n']:>5}")


def main():
    df = assemble()
    print(f"dataset: {len(df):,} active player-seasons | ADP coverage "
          f"{df.adp.notna().sum():,} rows ({df[df.adp.notna()].season.min()}-{df[df.adp.notna()].season.max()})")

    # projections (walk-forward where fitting is involved)
    df["naive_pts"]   = df["prior_half_ppr"]
    df["naive_ppg17"] = df["prior_ppg"] * 17
    print("fitting age-curve baseline (walk-forward) ...")
    df["age_curve"]   = age_curve_pred(df)
    print("retraining Model A walk-forward (LightGBM per position per season) ...")
    df["model_wf"]    = walk_forward_model(df) * 17
    df["finish_all"]  = finish_ranks(df)

    # drafted pool: ADP top-180 overall per season
    pool = df[df.adp.notna()].copy()
    pool["adp_overall"] = pool.groupby("season")["adp"].rank(method="first")
    pool = pool[pool.adp_overall <= POOL_SIZE]

    sources = {                       # name -> (col, ascending_rank_order)
        "naive_pts":   ("naive_pts", False),
        "naive_ppg17": ("naive_ppg17", False),
        "age_curve":   ("age_curve", False),
        "model_wf":    ("model_wf", False),
        "adp":         ("adp", True),
        "ecr":         ("ecr", True),
        "sleeper":     ("sleeper_pts_half_ppr", False),
    }

    all_results = {}
    for title, seasons in PANELS.items():
        p = pool[pool.season.isin(seasons)]
        panel = {}
        for name, (col, asc) in sources.items():
            if p[col].notna().sum() == 0:
                continue
            panel[name] = eval_source(p, col, asc)
        all_results[title] = panel
        print_panel(panel, title)

        # veterans-only slice: headline rho so the rookie penalty is visible
        vets = p[p.is_rookie == 0]
        print(f"\n  -- veterans only ({title}), Spearman rho --")
        print(f"  {'source':12} " + " ".join(f"{pos:>7}" for pos in POSITIONS))
        vet_res = {}
        for name, (col, asc) in sources.items():
            if vets[col].notna().sum() == 0:
                continue
            r = eval_source(vets, col, asc)
            vet_res[name] = r
            print(f"  {name:12} " + " ".join(
                f"{r[pos]['rho']:>7.3f}" if pos in r else f"{'-':>7}" for pos in POSITIONS))
        all_results[title + " [veterans]"] = vet_res

    OUT_JSON.write_text(json.dumps(all_results, indent=2, default=float))
    print(f"\nwrote {OUT_JSON.name}")
    return all_results


if __name__ == "__main__":
    main()
