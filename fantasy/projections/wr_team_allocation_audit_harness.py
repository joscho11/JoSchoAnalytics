"""WR TEAM-LEVEL ALLOCATION / CONCENTRATION AUDIT — read-only harness.

Governed by PREREG_wr_team_allocation_audit_2026-07-26.md. Fires ONCE.

This is an AUDIT, not an experiment on the model. It fits nothing, loads no pkl for scoring,
retrains nothing, and writes nothing into the repo. All generated output goes to
C:/tmp/wr_team_allocation_audit_2026-07-26.

  --check  structural only: git extraction + provenance, key/uniqueness checks, time boundaries,
           the synthetic planted-mis-allocation test, the structural power calculation, and the
           protected-artifact hashes. Prints NO historical OOF allocation result of any kind.
  --fire   the single frozen evaluation and the complete report.

Interpreter: AI_hedge_fund venv (bare `python` on this machine).
"""
import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ------------------------------------------------------------------------------------ CONSTANTS
HERE = Path(__file__).resolve().parent                    # fantasy/projections
REPO = HERE.parent.parent                                 # BettingEdgeContinued
SEAS = REPO / "fantasy" / "seasonal_projections"
RESULTS = HERE / "results"
MODELS = HERE / "models"

OUT = Path(r"C:/tmp/wr_team_allocation_audit_2026-07-26")

OOF_CSV = RESULTS / "wr_walkforward_predictions.csv"
PROJ_2026 = RESULTS / "wr_projection_2026.csv"
DATASET_NAME = "season_dataset_2014_2026.csv"
PREFIX_COMMIT = "3b4cde0"
PREFIX_MD5_HEAD = "8d301a19"                              # from the retrain prereg §10 check record
PREFIX_BYTES = 2977749

EVAL_SEASONS = [2021, 2022, 2023, 2024, 2025]
DEPLOY = 2026
SEED = 42
BOOT_DRAWS = 2000
BOARD_SEASON = 2026

# §5 gate bars — frozen, provenance in the prereg §2
GATE_A_BAR = -0.050
SEASON_BREADTH = 4
LEVEL_BAND = 0.05

# §5.1 structural power inputs — task specification, NOT estimated from the panel under test
POWER_CLUSTERS, POWER_SEASONS = 32, 5
POWER_EFFECT, POWER_SD = -0.05, 0.15
POWER_RHO_GRID = (0.0, 0.3, 0.6, 1.0)

RETRAIN_SCRATCH = Path(r"C:/Users/josep/AppData/Local/Temp/claude/"
                       r"c--Users-josep-Desktop-random-stuff-cowork-OS/"
                       r"19483edc-3155-4194-8790-1ec4281ff28f/scratchpad/retrain_eval")

PROTECTED_PINS = {                                        # prereg §9, carried from the retrain prereg §8
    "fantasy/projections/models/wr_veteran_model.pkl": "17dfbcf01054bdd5ce032f2b55df9ad2",
    "fantasy/projections/models/wr_rookie_model.pkl": "6c9a3f3ed02ce32c53594f383aade882",
    "fantasy/seasonal_projections/models/rookie_ppg_model.pkl": "872467b2295fce27761f9e04da01b6e8",
}
PROTECTED_EXTRA = [
    "fantasy/projections/models/qb_veteran_model.pkl",
    "fantasy/projections/models/rb_rookie_model.pkl",
    "fantasy/projections/models/rb_veteran_model.pkl",
    "fantasy/projections/models/te_rookie_model.pkl",
    "fantasy/projections/models/te_veteran_model.pkl",
    "fantasy/seasonal_projections/season_dataset_2014_2025.csv",
    "fantasy/seasonal_projections/season_dataset_2014_2026.csv",
    "fantasy/seasonal_projections/board_adp_live_2026.csv",
    "fantasy/projections/wr_player_scenarios_2026.csv",
    "draft_board_2026.py",
]


class Tee:
    """Mirror stdout into fire.log without swallowing it."""

    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, s):
        self.stdout.write(s)
        self.f.write(s)

    def flush(self):
        self.stdout.flush()
        self.f.flush()


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def self_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def snapshot() -> dict:
    out = {}
    for rel in list(PROTECTED_PINS) + PROTECTED_EXTRA:
        p = REPO / rel
        if p.exists():
            out[rel] = _md5(p)
    for f in sorted(RESULTS.glob("*.csv")):
        out[str(f.relative_to(REPO)).replace("\\", "/")] = _md5(f)
    return out


def assert_protected(before: dict, label: str):
    now = snapshot()
    drift = sorted(set(before) ^ set(now)) + [k for k in before if k in now and before[k] != now[k]]
    assert not drift, f"PROTECTED ARTIFACT DRIFT at {label} -> {drift}  (STOP AND REPORT)"
    bad = [f"{k}: {now[k]} != {v}" for k, v in PROTECTED_PINS.items() if k in now and now[k] != v]
    assert not bad, f"PROTECTED PIN MISMATCH: {bad}  (STOP AND REPORT)"
    return now


# ------------------------------------------------------------------------------------ PROVENANCE
def team_canon_map() -> dict:
    """TEAM_CANON sourced from build_season_dataset.py by AST literal-eval — the production mapping,
    not re-typed here, and read without importing the module (no nflreadpy import side effects)."""
    src = (SEAS / "build_season_dataset.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "TEAM_CANON" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("TEAM_CANON not found in build_season_dataset.py")


def materialise_prefix_dataset():
    """Extract the pre-fix dataset from git into scratch, read-only. Never touches the repo copy."""
    dst_dir = OUT / "prefix_seas"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / DATASET_NAME
    if not dst.exists():
        with open(dst, "wb") as fh:
            r = subprocess.run(
                ["git", "show", f"{PREFIX_COMMIT}:fantasy/seasonal_projections/{DATASET_NAME}"],
                cwd=REPO, stdout=fh)
        assert r.returncode == 0, "git show of the pre-fix dataset failed"
    blob = subprocess.run(
        ["git", "rev-parse", f"{PREFIX_COMMIT}:fantasy/seasonal_projections/{DATASET_NAME}"],
        cwd=REPO, capture_output=True, text=True).stdout.strip()
    md5, nbytes = _md5(dst), dst.stat().st_size
    assert md5.startswith(PREFIX_MD5_HEAD), f"pre-fix dataset md5 {md5} != {PREFIX_MD5_HEAD}..."
    assert nbytes == PREFIX_BYTES, f"pre-fix dataset {nbytes} bytes != {PREFIX_BYTES}"
    live = _md5(SEAS / DATASET_NAME)
    assert live != md5, "extracted pre-fix dataset is identical to the corrected file on disk"
    return dst, blob, md5, nbytes, live


# ------------------------------------------------------------------------------- FROZEN DEFINITIONS
def team_season_table(df: pd.DataFrame) -> pd.DataFrame:
    """§3 frozen definitions, one row per (season, team). `df` needs season/team/player_id/y/pred."""
    rows = []
    for (season, team), g in df.groupby(["season", "team"], sort=True):
        g = g.sort_values(["pred", "player_id"], ascending=[False, True])
        clip = g["pred"].clip(lower=0).to_numpy(float)
        y = g["y"].to_numpy(float)
        pt, at = float(clip.sum()), float(y.sum())
        rec = dict(season=int(season), team=team, n_wr=len(g),
                   n_pred_pos=int((g["pred"] > 0).sum()), n_actual_pos=int((g["y"] > 0).sum()),
                   team_pred_total=pt, team_actual_total=at,
                   team_signed_error=pt - at, team_abs_error=abs(pt - at),
                   pred_ok=pt > 0, actual_ok=at > 0)
        for k in (1, 2, 3, 6):
            if len(g) >= k and pt > 0 and at > 0:
                rec[f"pred_top{k}_share"] = float(clip[:k].sum() / pt)
                rec[f"actual_same{k}_share"] = float(y[:k].sum() / at)
                rec[f"alloc_err_top{k}"] = rec[f"pred_top{k}_share"] - rec[f"actual_same{k}_share"]
            else:
                rec[f"pred_top{k}_share"] = np.nan
                rec[f"actual_same{k}_share"] = np.nan
                rec[f"alloc_err_top{k}"] = np.nan
        # descriptive only, never admissible to a gate: outcome-selected ("oracle") top two
        rec["ORACLE_actual_top2_share"] = float(np.sort(np.clip(y, 0, None))[::-1][:2].sum() / at) \
            if (at > 0 and len(g) >= 2) else np.nan
        ps = clip / pt if pt > 0 else np.full(len(g), np.nan)
        as_ = np.clip(y, 0, None)
        as_ = as_ / as_.sum() if as_.sum() > 0 else np.full(len(g), np.nan)
        rec["pred_hhi"], rec["actual_hhi"] = _hhi(ps), _hhi(as_)
        rec["pred_entropy"], rec["actual_entropy"] = _norm_entropy(ps), _norm_entropy(as_)
        rec["allocation_error"] = rec["alloc_err_top2"]          # PRIMARY
        rows.append(rec)
    return pd.DataFrame(rows)


def _hhi(s):
    s = np.asarray(s, float)
    return float(np.nansum(s ** 2)) if np.isfinite(s).any() else np.nan


def _norm_entropy(s):
    s = np.asarray(s, float)
    if not np.isfinite(s).any() or len(s) < 2:
        return np.nan
    p = s[np.isfinite(s) & (s > 0)]
    if p.size == 0:
        return np.nan
    return float(-(p * np.log(p)).sum() / np.log(len(s)))


def rank_bucket_table(df: pd.DataFrame, ts: pd.DataFrame) -> pd.DataFrame:
    """Player-level residuals by within-team prediction rank (§3)."""
    ok = ts[ts.pred_ok & ts.actual_ok][["season", "team", "team_pred_total", "team_actual_total"]]
    d = df.merge(ok, on=["season", "team"], how="inner").copy()
    d = d.sort_values(["season", "team", "pred", "player_id"], ascending=[True, True, False, True])
    d["pred_rank"] = d.groupby(["season", "team"]).cumcount() + 1
    d["pred_share"] = d["pred"].clip(lower=0) / d["team_pred_total"]
    d["actual_share"] = d["y"] / d["team_actual_total"]
    d["share_resid"] = d["actual_share"] - d["pred_share"]
    d["point_resid"] = d["y"] - d["pred"].clip(lower=0)
    d["bucket"] = pd.cut(d["pred_rank"], [0, 1, 2, 3, 6, 10 ** 6],
                         labels=["rank1", "rank2", "rank3", "rank4-6", "rank7+"])
    return d


def cluster_bootstrap_mean(values, clusters, draws=BOOT_DRAWS, seed=SEED):
    """95% percentile interval for the mean, resampling `clusters` with replacement."""
    values = np.asarray(values, float)
    clusters = np.asarray(clusters)
    keep = np.isfinite(values)
    values, clusters = values[keep], clusters[keep]
    if values.size == 0:
        return np.nan, np.nan, np.nan
    uniq = np.unique(clusters)
    pos = {c: np.where(clusters == c)[0] for c in uniq}
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    for k in range(draws):
        sel = np.concatenate([pos[c] for c in rng.choice(uniq, size=uniq.size, replace=True)])
        out[k] = values[sel].mean()
    return float(values.mean()), float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


# ------------------------------------------------------------------------------------ PANEL BUILD
def load_primary_panel(prefix_csv: Path, canon: dict, verbose=True):
    oof = pd.read_csv(OOF_CSV)
    assert set(["season", "player_id", "y", "pred"]).issubset(oof.columns), "OOF schema changed"
    n_raw = len(oof)
    assert not oof.duplicated(["player_id", "season"]).any(), "OOF key (player_id, season) not unique"
    oof = oof[oof.season.isin(EVAL_SEASONS)].copy()

    ds = pd.read_csv(prefix_csv, usecols=["player_id", "season", "player", "position", "team"])
    ds = ds[ds.position == "WR"].copy()
    assert not ds.duplicated(["player_id", "season"]).any(), \
        "pre-fix dataset key (player_id, season) not unique within WR"
    ds["team_raw"] = ds["team"]
    ds["team"] = ds["team"].replace(canon)
    remapped = ds.loc[ds.team_raw.notna() & (ds.team_raw != ds.team), "team_raw"].value_counts()

    m = oof.merge(ds[["player_id", "season", "team"]], on=["player_id", "season"], how="left")
    unmatched = m[m.team.isna()]
    panel = m[m.team.notna()].copy()
    if verbose:
        print(f"  OOF rows total {n_raw} | in 2021-2025 {len(oof)} | matched with a team {len(panel)} "
              f"| unmatched/no-team {len(unmatched)}")
        if len(remapped):
            print(f"  TEAM_CANON remapped codes: {dict(remapped)}")
        else:
            print("  TEAM_CANON remapped codes: none (pre-fix WR team codes already canonical)")
    return panel, unmatched, oof


# ------------------------------------------------------------------------------------- SYNTHETIC
def synthetic_probe():
    """Planted mis-allocation with known truth (prereg §8). A harness that cannot detect a planted
    defect cannot report its absence."""
    rows = []
    # T_CONC: prediction perfectly concentrated in 2 of 6, outcome perfectly uniform -> alloc_err = +2/3
    for i in range(6):
        rows.append(dict(season=2021, team="T_CONC", player_id=f"c{i}",
                         pred=100.0 if i < 2 else 0.0, y=60.0))
    # T_DIFF: prediction perfectly uniform over 6, outcome entirely in the 2 predicted leaders
    for i in range(6):
        rows.append(dict(season=2021, team="T_DIFF", player_id=f"d{i}",
                         pred=100.0 - i, y=180.0 if i < 2 else 0.0))
    # T_EXACT: prediction == outcome -> alloc_err exactly 0
    for i in range(6):
        rows.append(dict(season=2021, team="T_EXACT", player_id=f"e{i}", pred=50.0 * (6 - i),
                         y=50.0 * (6 - i)))
    # T_NEG: a negative prediction must clip, not corrupt the denominator
    for i in range(4):
        rows.append(dict(season=2021, team="T_NEG", player_id=f"n{i}",
                         pred=[80.0, 20.0, 0.0, -30.0][i], y=[80.0, 20.0, 0.0, 0.0][i]))
    syn = pd.DataFrame(rows)
    ts = team_season_table(syn)
    got = ts.set_index("team")["allocation_error"].to_dict()
    exp = {"T_CONC": 1.0 - 2 / 6, "T_DIFF": (100 + 99) / 585 - 1.0, "T_EXACT": 0.0,
           "T_NEG": 1.0 - 1.0}
    ok = all(abs(got[k] - exp[k]) < 1e-12 for k in exp)
    rb = rank_bucket_table(syn, ts)
    conc = rb[(rb.team == "T_CONC")].groupby("bucket", observed=True)["share_resid"].mean()
    diff = rb[(rb.team == "T_DIFF")].groupby("bucket", observed=True)["share_resid"].mean()
    signs_ok = (conc.get("rank1", 0) < 0) and (diff.get("rank1", 0) > 0)
    neg_ok = abs(ts.set_index("team").loc["T_NEG", "team_pred_total"] - 100.0) < 1e-12
    print("  SYNTHETIC planted mis-allocation:")
    for k in ("T_CONC", "T_DIFF", "T_EXACT", "T_NEG"):
        print(f"    {k:8s} allocation_error {got[k]:+.6f}  (expected {exp[k]:+.6f})")
    print(f"    rank-1 share residual: over-concentrated team {conc.get('rank1', float('nan')):+.4f} (<0) | "
          f"under-concentrated team {diff.get('rank1', float('nan')):+.4f} (>0)")
    print(f"    negative-prediction clipping: team_pred_total = "
          f"{ts.set_index('team').loc['T_NEG', 'team_pred_total']:.1f} (expected 100.0)")
    print(f"    -> {'PASS' if (ok and signs_ok and neg_ok) else 'FAIL'}")
    assert ok and signs_ok and neg_ok, "SYNTHETIC PROBE FAILED — harness cannot detect mis-allocation"


def power_calculation():
    """§5.1 — structure only. No observed allocation error enters this."""
    from math import erf, sqrt
    n = POWER_CLUSTERS * POWER_SEASONS
    print(f"  STRUCTURAL POWER ({POWER_CLUSTERS} clusters x {POWER_SEASONS} seasons = {n} team-seasons, "
          f"effect {POWER_EFFECT:+.3f}, assumed SD {POWER_SD})")
    print("    rho   design_eff   n_eff    SE      MDE(80%)   power@effect")
    rows = []
    for rho in POWER_RHO_GRID:
        deff = 1 + (POWER_SEASONS - 1) * rho
        n_eff = n / deff
        se = POWER_SD / sqrt(n_eff)
        mde = 2.802 * se
        z = abs(POWER_EFFECT) / se - 1.959964
        power = 0.5 * (1 + erf(z / sqrt(2)))
        rows.append(dict(rho=rho, design_effect=deff, n_eff=n_eff, se=se, mde_80=mde, power=power))
        print(f"    {rho:4.1f}  {deff:8.2f}  {n_eff:7.1f}  {se:.5f}  {mde:+.5f}   {power:6.3f}")
    return rows


# ------------------------------------------------------------------------------------ 2026 TABLES
def board_visible_ids():
    ds = pd.read_csv(SEAS / DATASET_NAME,
                     usecols=["player_id", "season", "player", "position", "adp_half_ppr"])
    b = ds[(ds.season == BOARD_SEASON) & ds.adp_half_ppr.notna()].drop_duplicates("player_id")
    return set(b.player_id), len(b)


def table_2026():
    p = pd.read_csv(PROJ_2026)
    vis, n_board = board_visible_ids()
    p["board_visible"] = p.player_id.isin(vis)
    rows = []
    for team, g in p.dropna(subset=["team"]).groupby("team", sort=True):
        g = g.sort_values(["projection", "player_id"], ascending=[False, True])
        clip = g["projection"].clip(lower=0).to_numpy(float)
        tot = float(clip.sum())
        v = g[g.board_visible]
        rec = dict(team=team, n_wr=len(g), room_points=tot,
                   n_board_visible=int(len(v)),
                   board_visible_points=float(v["projection"].clip(lower=0).sum()))
        rec["board_visible_share_of_room"] = rec["board_visible_points"] / tot if tot > 0 else np.nan
        for k in (1, 2, 3, 6):
            rec[f"proj_top{k}_share"] = float(clip[:k].sum() / tot) if (tot > 0 and len(g) >= k) else np.nan
        s = clip / tot if tot > 0 else np.full(len(g), np.nan)
        rec["proj_hhi"], rec["proj_entropy"] = _hhi(s), _norm_entropy(s)
        rec["top1"] = f"{g.iloc[0]['player']} {g.iloc[0]['projection']:.1f}" if len(g) else ""
        rec["top2"] = f"{g.iloc[1]['player']} {g.iloc[1]['projection']:.1f}" if len(g) > 1 else ""
        rows.append(rec)
    return pd.DataFrame(rows), p, n_board


def case_study(p26):
    rows = []
    for team in ("WAS", "TEN"):
        g = p26[p26.team == team].sort_values(["projection", "player_id"], ascending=[False, True])
        tot = float(g["projection"].clip(lower=0).sum())
        for i, (_, r) in enumerate(g.iterrows(), start=1):
            rows.append(dict(team=team, pred_rank=i, player=r["player"], player_id=r["player_id"],
                             is_rookie=r.get("is_rookie"), projection=r["projection"],
                             sleeper=r.get("sleeper"), adp_pos_rank=r.get("adp_pos_rank"),
                             board_visible=bool(r["board_visible"]),
                             share_of_room=(max(r["projection"], 0) / tot) if tot > 0 else np.nan,
                             room_points=tot))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------- SECONDARY PANEL
def find_corrected_panel():
    """Locate a COMPLETE new corrected WR OOF panel produced by the corrected-data retrain.
    Returns (DataFrame|None, note)."""
    if not RETRAIN_SCRATCH.exists():
        return None, "retrain scratch directory absent"
    log = RETRAIN_SCRATCH / "fire.log"
    terminal = "unknown"
    if log.exists():
        tail = log.read_text(encoding="utf-8", errors="replace")
        terminal = "log present"
        if "TE ===" in tail or "FIRE COMPLETE" in tail:
            terminal = "log reached the final position"
    cands = []
    for f in list(RETRAIN_SCRATCH.glob("*.csv")) + list(RETRAIN_SCRATCH.glob("*.parquet")):
        try:
            d = pd.read_parquet(f) if f.suffix == ".parquet" else pd.read_csv(f)
        except Exception:
            continue
        if {"player_id", "season", "y", "pred"}.issubset(d.columns) and \
                set(EVAL_SEASONS).issubset(set(pd.to_numeric(d["season"], errors="coerce").dropna().astype(int))):
            cands.append((f, d))
    if not cands:
        return None, (f"no complete NEW corrected WR OOF panel found in the retrain scratch "
                      f"({terminal}); the retrain harness writes only deploy_move_*.csv and fire.log")
    f, d = cands[0]
    return d, f"corrected NEW panel taken from {f.name}"


# ------------------------------------------------------------------------------------------ MODES
def run_check():
    print("=" * 92)
    print("WR TEAM-ALLOCATION AUDIT — --check  (STRUCTURAL ONLY; no historical OOF allocation result)")
    print("=" * 92)
    OUT.mkdir(parents=True, exist_ok=True)
    before = snapshot()
    print(f"\nharness SHA256: {self_sha256()}")
    print(f"protected artifacts snapshotted: {len(before)} files; pinned {len(PROTECTED_PINS)} verified")

    print("\n--- PROVENANCE ---")
    canon = team_canon_map()
    print(f"  TEAM_CANON (AST from build_season_dataset.py): {canon}")
    dst, blob, md5, nbytes, live = materialise_prefix_dataset()
    print(f"  pre-fix dataset git {PREFIX_COMMIT} -> {dst}")
    print(f"    blob {blob[:12]}  md5 {md5}  bytes {nbytes:,}")
    print(f"    corrected file on disk md5 {live}  (asserted DIFFERENT)")

    print("\n--- KEYS / STRUCTURE (counts only) ---")
    panel, unmatched, oof = load_primary_panel(dst, canon)
    print(f"  seasons present: {sorted(panel.season.unique())}")
    assert set(panel.season.unique()) <= set(EVAL_SEASONS), "a season outside 2021-2025 entered the panel"
    assert panel.season.min() >= 2021, "sealed-season fence: no season < 2016 may be scored"
    print(f"  teams: {panel.team.nunique()} | team-seasons: {panel.groupby(['season','team']).ngroups}")
    print(f"  arms merged: {dict(panel.grp.value_counts())}")
    if len(unmatched):
        print(f"  UNMATCHED OOF rows ({len(unmatched)}): "
              f"{', '.join(unmatched['player'].head(10))}")
    print(f"  2026 projection rows: {len(pd.read_csv(PROJ_2026))}")
    vis, n_board = board_visible_ids()
    print(f"  board universe (2026 rows with ADP, all positions): {n_board}")

    print("\n--- SYNTHETIC ---")
    synthetic_probe()

    print("\n--- POWER ---")
    power_calculation()

    print("\n--- SECONDARY PANEL AVAILABILITY ---")
    sec, note = find_corrected_panel()
    print(f"  {'FOUND' if sec is not None else 'NOT AVAILABLE'}: {note}")

    assert_protected(before, "--check end")
    print("\nprotected artifacts byte-identical before and after --check")
    print("CHECK: PASS  (no historical OOF allocation statistic was computed or printed)")


def _gate_block(ts, label):
    adm = ts[ts.allocation_error.notna()].copy()
    mean, lo, hi = cluster_bootstrap_mean(adm.allocation_error, adm.team)
    per_season = adm.groupby("season")["allocation_error"].agg(["mean", "size"])
    n_neg = int((per_season["mean"] < 0).sum())
    level = float(adm.team_signed_error.sum() / adm.team_actual_total.sum())   # §5: admissible only
    print(f"\n  [{label}] admissible team-seasons {len(adm)} of {len(ts)}")
    print(f"  A  pooled mean allocation_error {mean:+.5f}  (bar <= {GATE_A_BAR:+.3f})  "
          f"-> {'PASS' if mean <= GATE_A_BAR else 'FAIL'}")
    print(f"  B  team-clustered bootstrap 95% [{lo:+.5f}, {hi:+.5f}] "
          f"({BOOT_DRAWS} draws, seed {SEED}, {adm.team.nunique()} clusters)  "
          f"-> {'PASS' if hi < 0 else 'FAIL'}")
    print("  C  per-season mean allocation_error:")
    for s, r in per_season.iterrows():
        print(f"       {int(s)}  {r['mean']:+.5f}  (n={int(r['size'])})")
    print(f"     negative in {n_neg} of {len(per_season)}  (bar >= {SEASON_BREADTH})  "
          f"-> {'PASS' if n_neg >= SEASON_BREADTH else 'FAIL'}")
    return dict(mean=mean, lo=lo, hi=hi, n_adm=len(adm), n_teams=int(adm.team.nunique()),
                per_season={int(s): float(r["mean"]) for s, r in per_season.iterrows()},
                n_seasons_negative=n_neg, level_bias=level,
                gate_A=bool(mean <= GATE_A_BAR), gate_B=bool(hi < 0),
                gate_C=bool(n_neg >= SEASON_BREADTH))


def _bucket_block(rb, label):
    print(f"\n  [{label}] rank-bucket residuals (actual_share - pred_share)")
    out = {}
    for b in ["rank1", "rank2", "rank3", "rank4-6", "rank7+"]:
        sub = rb[rb.bucket == b]
        if not len(sub):
            continue
        m, lo, hi = cluster_bootstrap_mean(sub.share_resid, sub.team)
        pm = float(sub.point_resid.mean())
        out[b] = dict(n=len(sub), share_resid=m, lo=lo, hi=hi, point_resid=pm)
        print(f"    {b:8s} n={len(sub):5d}  share_resid {m:+.5f}  95% [{lo:+.5f}, {hi:+.5f}]  "
              f"point_resid {pm:+7.2f}")
    r12 = rb[rb.bucket.isin(["rank1", "rank2"])]
    m12, lo12, hi12 = cluster_bootstrap_mean(r12.share_resid, r12.team)
    r7 = rb[rb.bucket == "rank7+"]
    m7, lo7, hi7 = cluster_bootstrap_mean(r7.share_resid, r7.team) if len(r7) else (np.nan,) * 3
    d_pos = m12 > 0
    d_neg = (m7 < 0) if np.isfinite(m7) else False
    d_ci = (lo12 > 0) or (hi12 < 0)
    print(f"    ranks1-2 combined n={len(r12)}  {m12:+.5f}  95% [{lo12:+.5f}, {hi12:+.5f}]  "
          f"(must be > 0 and exclude zero)")
    print(f"    ranks7+           n={len(r7)}  {m7:+.5f}  95% [{lo7:+.5f}, {hi7:+.5f}]  (must be < 0)")
    print(f"  D  -> {'PASS' if (d_pos and d_neg and d_ci) else 'FAIL'}"
          f"   [rank12>0 {d_pos} | rank7+<0 {d_neg} | rank12 CI excludes 0 {d_ci}]")
    out["_gate_D"] = dict(rank12_mean=m12, rank12_lo=lo12, rank12_hi=hi12, rank12_n=len(r12),
                          rank7_mean=float(m7), rank7_lo=float(lo7), rank7_hi=float(hi7),
                          rank7_n=len(r7), gate_D=bool(d_pos and d_neg and d_ci))
    return out


def run_fire():
    OUT.mkdir(parents=True, exist_ok=True)
    tee = Tee(OUT / "fire.log")
    sys.stdout = tee
    try:
        sha = self_sha256()
        print("=" * 92)
        print("WR TEAM-ALLOCATION AUDIT — --fire  (ONE SHOT, frozen)")
        print(f"harness SHA256: {sha}")
        print("prereg: fantasy/projections/PREREG_wr_team_allocation_audit_2026-07-26.md")
        print("=" * 92)
        before = snapshot()
        summary = {"harness_sha256": sha, "prereg": "PREREG_wr_team_allocation_audit_2026-07-26.md"}

        canon = team_canon_map()
        dst, blob, md5, nbytes, live = materialise_prefix_dataset()
        print(f"\nPROVENANCE  pre-fix dataset git {PREFIX_COMMIT} blob {blob[:12]} md5 {md5} "
              f"({nbytes:,} bytes); corrected-on-disk md5 {live}")
        summary["provenance"] = dict(commit=PREFIX_COMMIT, blob=blob, prefix_md5=md5,
                                     prefix_bytes=nbytes, corrected_on_disk_md5=live,
                                     team_canon=canon)

        print("\n" + "-" * 92)
        print("PRIMARY PANEL — shipped OOF (wr_walkforward_predictions.csv), 2021-2025")
        print("-" * 92)
        panel, unmatched, oof = load_primary_panel(dst, canon)
        ts = team_season_table(panel)
        adm = ts[ts.allocation_error.notna()]
        summary["panel"] = dict(oof_rows_total=len(oof), matched=len(panel), unmatched=len(unmatched),
                                unmatched_players=unmatched["player"].tolist(),
                                team_seasons=len(ts), teams=int(ts.team.nunique()))

        degen = ts[~(ts.pred_ok & ts.actual_ok) | (ts.n_wr < 2)]
        print(f"\nDEGENERATE / INCOMPLETE team-seasons: {len(degen)}")
        if len(degen):
            print(degen[["season", "team", "n_wr", "team_pred_total", "team_actual_total"]]
                  .to_string(index=False))
        summary["degenerate_team_seasons"] = degen[["season", "team", "n_wr", "team_pred_total",
                                                    "team_actual_total"]].to_dict("records")

        print("\nUNIVERSE — WR rows per team-season (the historical-vs-deploy mismatch, §7.3)")
        u = ts.groupby("season")[["n_wr", "n_actual_pos", "n_pred_pos"]].mean()
        u["team_seasons"] = ts.groupby("season").size()
        print(u.round(2).to_string())
        t26, p26, n_board = table_2026()
        print(f"  2026 deploy: {len(p26)} WR rows over {t26.team.nunique()} teams = "
              f"{len(p26)/max(t26.team.nunique(),1):.2f} WR/team "
              f"(historical mean {ts.n_wr.mean():.2f}/team-season, "
              f"of which {ts.n_actual_pos.mean():.2f} scored > 0)")
        summary["universe"] = dict(
            hist_wr_per_team_season=float(ts.n_wr.mean()),
            hist_actual_pos_per_team_season=float(ts.n_actual_pos.mean()),
            deploy_wr_rows=len(p26), deploy_teams=int(t26.team.nunique()),
            deploy_wr_per_team=float(len(p26) / max(t26.team.nunique(), 1)),
            per_season=u.round(4).reset_index().to_dict("records"))

        print("\n" + "=" * 92)
        print("PRE-REGISTERED GATES A-D — PRIMARY PANEL")
        print("=" * 92)
        g = _gate_block(ts, "PRIMARY")
        rb = rank_bucket_table(panel, ts)
        bk = _bucket_block(rb, "PRIMARY")
        gate_D = bk["_gate_D"]["gate_D"]

        passed = g["gate_A"] and g["gate_B"] and g["gate_C"] and gate_D
        level = g["level_bias"]
        if passed:
            verdict = ("GENERIC UNDER-CONCENTRATION CONFIRMED — ALLOCATION-ONLY" if abs(level) <= LEVEL_BAND
                       else "GENERIC UNDER-CONCENTRATION CONFIRMED — MIXED ALLOCATION + LEVEL")
        else:
            verdict = "NO GENERIC CONCENTRATION DEFECT"

        print("\n" + "-" * 92)
        print("TEAM-TOTAL BIAS (the mechanism classifier)")
        print("-" * 92)
        print(f"  pooled predicted WR points  {adm.team_pred_total.sum():,.1f}")
        print(f"  pooled actual    WR points  {adm.team_actual_total.sum():,.1f}")
        print(f"  pooled signed error         {adm.team_signed_error.sum():+,.1f}  "
              f"= {100*level:+.2f}% of actual   (band +/-{100*LEVEL_BAND:.0f}%)")
        print(f"  mean |team error| per team-season  {adm.team_abs_error.mean():.2f}")
        if len(adm) != len(ts):
            all_lv = float(ts.team_signed_error.sum() / ts.team_actual_total.sum())
            print(f"  (all {len(ts)} team-seasons incl. degenerate: {100*all_lv:+.2f}%)")
        summary["level"] = dict(pred_total=float(adm.team_pred_total.sum()),
                                actual_total=float(adm.team_actual_total.sum()),
                                signed_error=float(adm.team_signed_error.sum()), level_bias=level,
                                mean_abs_team_error=float(adm.team_abs_error.mean()))

        print("\n" + "-" * 92)
        print("CONCENTRATION, PREDICTED vs ACTUAL (descriptive; top-K by PREDICTION identity)")
        print("-" * 92)
        for k in (1, 2, 3, 6):
            pk, ak = f"pred_top{k}_share", f"actual_same{k}_share"
            sub = ts[ts[pk].notna()]
            print(f"  top{k}: predicted mean {sub[pk].mean():.4f} median {sub[pk].median():.4f} | "
                  f"actual(same players) mean {sub[ak].mean():.4f} median {sub[ak].median():.4f} | "
                  f"alloc_err mean {sub[f'alloc_err_top{k}'].mean():+.4f}")
        print(f"  ORACLE (outcome-selected top-two) actual share mean "
              f"{ts.ORACLE_actual_top2_share.mean():.4f} median {ts.ORACLE_actual_top2_share.median():.4f}"
              "   [DESCRIPTIVE CONTEXT ONLY — inadmissible to any gate]")
        print(f"  HHI      predicted {adm.pred_hhi.mean():.4f} | actual {adm.actual_hhi.mean():.4f}")
        print(f"  entropy  predicted {adm.pred_entropy.mean():.4f} | actual {adm.actual_entropy.mean():.4f}")
        summary["concentration"] = {
            f"top{k}": dict(pred_mean=float(ts[f"pred_top{k}_share"].mean()),
                            actual_mean=float(ts[f"actual_same{k}_share"].mean()),
                            alloc_err_mean=float(ts[f"alloc_err_top{k}"].mean())) for k in (1, 2, 3, 6)}
        summary["concentration"]["ORACLE_actual_top2_mean_DESCRIPTIVE"] = \
            float(ts.ORACLE_actual_top2_share.mean())
        summary["concentration"]["hhi_pred"] = float(adm.pred_hhi.mean())
        summary["concentration"]["hhi_actual"] = float(adm.actual_hhi.mean())
        summary["concentration"]["entropy_pred"] = float(adm.pred_entropy.mean())
        summary["concentration"]["entropy_actual"] = float(adm.actual_entropy.mean())

        print("\n" + "=" * 92)
        print(f"PRIMARY VERDICT: {verdict}")
        print("=" * 92)
        summary["gates"] = dict(**g, gate_D=gate_D, buckets=bk, verdict=verdict)

        # ------------------------------------------------------------------ 2026 diagnostics
        print("\n" + "-" * 92)
        print("2026 DEPLOY CONCENTRATION — all 32 teams, sorted by top-two share (DIAGNOSTIC, no gate)")
        print("-" * 92)
        # Three clearly-labelled historical reference distributions for the 2026 comparison.
        refs = {
            "ACTUAL_oracle_top2": adm.ORACLE_actual_top2_share,      # outcome-selected: the 67.1% family
            "ACTUAL_of_pred_selected_top2": adm.actual_same2_share,  # same identities the model picked
            "PREDICTED_oof_top2": adm.pred_top2_share,               # apples-to-apples vs a 2026 projection
        }
        hist_med = float(refs["ACTUAL_oracle_top2"].median())
        hist_p10 = float(refs["ACTUAL_oracle_top2"].quantile(0.10))
        show = t26.sort_values("proj_top2_share")
        print(show[["team", "n_wr", "room_points", "proj_top1_share", "proj_top2_share",
                    "proj_top3_share", "proj_top6_share", "n_board_visible",
                    "board_visible_points", "board_visible_share_of_room"]]
              .to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        print(f"\n  2026 projected top-two share: median {t26.proj_top2_share.median():.3f}")
        print("  historical reference distributions (2021-2025 primary panel) and 2026 teams below each:")
        ref_out = {}
        for name, series in refs.items():
            med, p10, p25 = (float(series.median()), float(series.quantile(0.10)),
                             float(series.quantile(0.25)))
            below10 = int((t26.proj_top2_share < p10).sum())
            below25 = int((t26.proj_top2_share < p25).sum())
            print(f"    {name:30s} median {med:.3f}  p10 {p10:.3f}  p25 {p25:.3f}  ->  "
                  f"2026 teams below p10: {below10}/{len(t26)}   below p25: {below25}/{len(t26)}")
            ref_out[name] = dict(median=med, p10=p10, p25=p25, teams_below_p10=below10,
                                 teams_below_p25=below25)
        n_below = ref_out["ACTUAL_oracle_top2"]["teams_below_p10"]
        print("\n2026 sorted by BOARD-VISIBLE share of the modeled room:")
        print(t26.sort_values("board_visible_share_of_room")
              [["team", "n_wr", "room_points", "n_board_visible", "board_visible_points",
                "board_visible_share_of_room", "proj_top2_share"]]
              .to_string(index=False, float_format=lambda x: f"{x:.3f}"))
        summary["deploy_2026"] = dict(
            hist_actual_top2_median=hist_med, hist_actual_top2_p10=hist_p10,
            historical_references=ref_out,
            proj_top2_median=float(t26.proj_top2_share.median()),
            teams_below_hist_p10=n_below, n_teams=int(len(t26)),
            board_universe_rows=n_board,
            board_visible_wr=int(t26.n_board_visible.sum()),
            board_visible_points=float(t26.board_visible_points.sum()),
            modeled_room_points=float(t26.room_points.sum()),
            board_visible_share_of_all_wr_points=float(
                t26.board_visible_points.sum() / t26.room_points.sum()))
        print(f"\n  BOARD VISIBILITY (league-wide): {int(t26.n_board_visible.sum())} of {len(p26)} "
              f"modeled WRs visible; {t26.board_visible_points.sum():,.1f} of "
              f"{t26.room_points.sum():,.1f} modeled WR points = "
              f"{100*t26.board_visible_points.sum()/t26.room_points.sum():.1f}%")

        cs = case_study(p26)
        print("\n" + "-" * 92)
        print("WASHINGTON / TENNESSEE CASE STUDY (DIAGNOSTIC)")
        print("-" * 92)
        for team in ("WAS", "TEN"):
            sub = cs[cs.team == team]
            room = float(sub.room_points.iloc[0])
            t2 = float(sub.head(2).projection.clip(lower=0).sum())
            vis = sub[sub.board_visible]
            print(f"\n  {team}: {len(sub)} modeled WRs, room {room:.1f}; "
                  f"model top two {t2:.1f} = {100*t2/room:.1f}%; "
                  f"board-visible {len(vis)} totalling {vis.projection.sum():.1f} = "
                  f"{100*vis.projection.sum()/room:.1f}% of the room")
            print(sub[["pred_rank", "player", "projection", "share_of_room", "board_visible",
                       "adp_pos_rank", "sleeper"]].to_string(index=False,
                                                             float_format=lambda x: f"{x:.3f}"))

        # ------------------------------------------------------------------ secondary panel
        print("\n" + "-" * 92)
        print("SECONDARY PANEL — corrected-data retrain (REPORT-ONLY; cannot change the verdict)")
        print("-" * 92)
        sec, note = find_corrected_panel()
        if sec is None:
            print(f"  NOT AVAILABLE: {note}")
            summary["secondary"] = dict(available=False, note=note)
        else:
            print(f"  {note}")
            sec = sec[sec.season.isin(EVAL_SEASONS)].copy()
            ds = pd.read_csv(dst, usecols=["player_id", "season", "position", "team"])
            ds = ds[ds.position == "WR"]
            ds["team"] = ds["team"].replace(canon)
            sec = sec.merge(ds[["player_id", "season", "team"]], on=["player_id", "season"], how="left")
            sec = sec[sec.team.notna()]
            ts2 = team_season_table(sec)
            g2 = _gate_block(ts2, "SECONDARY")
            rb2 = rank_bucket_table(sec, ts2)
            bk2 = _bucket_block(rb2, "SECONDARY")
            agree = (g2["gate_A"] == g["gate_A"] and g2["gate_B"] == g["gate_B"]
                     and g2["gate_C"] == g["gate_C"] and bk2["_gate_D"]["gate_D"] == gate_D)
            print(f"\n  SECONDARY agrees with PRIMARY on all four gates: {agree}")
            summary["secondary"] = dict(available=True, note=note, gates=dict(**g2, buckets=bk2),
                                        agrees_with_primary=agree)
            ts2.to_csv(OUT / "team_season_corrected_secondary.csv", index=False)
            rb2.groupby("bucket", observed=True).agg(
                n=("share_resid", "size"), share_resid=("share_resid", "mean"),
                point_resid=("point_resid", "mean")).reset_index().to_csv(
                OUT / "rank_bucket_corrected_secondary.csv", index=False)

        # ------------------------------------------------------------------ outputs + integrity
        ts.to_csv(OUT / "team_season_primary.csv", index=False)
        rbagg = rb.groupby("bucket", observed=True).agg(
            n=("share_resid", "size"), share_resid=("share_resid", "mean"),
            point_resid=("point_resid", "mean"),
            pred_share=("pred_share", "mean"), actual_share=("actual_share", "mean")).reset_index()
        rbagg.to_csv(OUT / "rank_bucket_primary.csv", index=False)
        t26.to_csv(OUT / "team_2026.csv", index=False)
        cs.to_csv(OUT / "washington_tennessee_case_study.csv", index=False)

        after = assert_protected(before, "--fire end")
        summary["protected"] = dict(files=len(after), drift=0,
                                    pins={k: after.get(k) for k in PROTECTED_PINS})
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\nprotected artifacts byte-identical before and after --fire ({len(after)} files, drift 0)")
        print(f"outputs -> {OUT}")
        print(f"\nFINAL: {verdict}")
    finally:
        sys.stdout = tee.stdout
        tee.f.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--fire", action="store_true")
    a = ap.parse_args()
    if a.check:
        run_check()
    elif a.fire:
        run_fire()
    else:
        raise SystemExit("pass --check or --fire")


if __name__ == "__main__":
    main()
