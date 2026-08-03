"""Part B — feature matrix (5 groups) joined to the panel (BLIND build; NO feature-vs-target).

Groups (prereg §4), all point-in-time AT DRAFT:
  1 DRAFT CAPITAL  draft_pick(overall), draft_round, log_pick               [gsis]
  2 COMBINE        forty,vertical,broad_jump,cone,shuttle,bench,ht_in,wt,bmi,speed_score [pfr->gsis]
  5 AGE            age at draft                                              [gsis]
  3 COLLEGE BOX    cfb_* from college_features.csv                          [norm_name]
  4 COLLEGE PFF    position-specific final-college-season grades            [norm_name, final szn]

Outputs (scratchpad only): feat_hit.parquet, feat_scoring.parquet.
Prints ONLY structural coverage/dtype asserts. NEVER a feature-vs-target statistic.
Raw-PFF columns land only in this temp scratchpad (never a git repo / never public).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import nflreadpy as nfl

sys.path.insert(0, r"c:/Users/josep/Desktop/random_stuff/cowork_OS/JoSchoAnalytics/fantasy/seasonal_projections")
from _utils import norm_name  # repo-consistent normalization

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 200)

HERE = Path(__file__).resolve().parent
REPO = Path(r"c:/Users/josep/Desktop/random_stuff/cowork_OS/JoSchoAnalytics/fantasy/seasonal_projections")
PFF = REPO / "pff"
SKILL = ["QB", "RB", "WR", "TE"]
PFF_SEASONS = list(range(2014, 2026))

# concrete pinned PFF feature columns per position (build mechanics; documented)
PFF_RECV = ["grades_offense", "grades_pass_route", "yprr", "avg_depth_of_target",
            "contested_catch_rate", "drop_rate", "yards_after_catch_per_reception",
            "targeted_qb_rating", "routes", "receptions", "yards", "touchdowns", "avoided_tackles"]
PFF_RUSH = ["grades_run", "grades_offense", "elusive_rating", "breakaway_percent",
            "elu_yco", "avoided_tackles", "attempts", "yards_after_contact_per_attempt",
            "first_downs", "touchdowns"]
PFF_PASS = ["grades_pass", "grades_offense", "btt_rate", "avg_time_to_throw",
            "accuracy_percent", "completion_percent", "pressure_to_sack_rate",
            "avg_depth_of_target", "qb_rating", "touchdowns"]


def pdf(x):
    try:
        return x.to_pandas()
    except AttributeError:
        return x


def _load_pff(kind, cols):
    """Concat a PFF college summary table across seasons; keep final-season row per norm_name."""
    frames = []
    for yr in PFF_SEASONS:
        f = PFF / f"college_{yr}" / f"college_{kind}_summary_{yr}.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f)
        d["season"] = yr
        frames.append(d)
    if not frames:
        return pd.DataFrame(columns=["norm_name"])
    alld = pd.concat(frames, ignore_index=True)
    alld["norm_name"] = alld["player"].map(norm_name)
    keep = [c for c in cols if c in alld.columns]
    idx = alld.groupby("norm_name")["season"].idxmax()          # FINAL college season row
    fin = alld.loc[idx, ["norm_name"] + keep].copy()
    fin = fin.rename(columns={c: f"pff_{kind}_{c}" for c in keep})
    return fin.drop_duplicates("norm_name")


def build_features(panel):
    p = panel.copy()

    # --- group 1 draft capital (panel already has round/pick) + group 5 age/name from draft ---
    draft = pdf(nfl.load_draft_picks()).dropna(subset=["gsis_id"]).drop_duplicates("gsis_id")
    dcap = draft[["gsis_id", "age", "pfr_player_name", "pfr_player_id"]].copy()
    p = p.merge(dcap, on="gsis_id", how="left")
    p["draft_pick"] = p["pick"]
    p["draft_round"] = p["round"]
    p["log_pick"] = np.log(p["pick"].clip(lower=1))
    p["norm_name"] = p["pfr_player_name"].map(norm_name)

    # --- group 2 combine (pfr_id -> gsis) ---
    comb = pdf(nfl.load_combine()).dropna(subset=["pfr_id"]).drop_duplicates("pfr_id").copy()
    def ht_to_in(s):
        if isinstance(s, str) and "-" in s:
            a, b = s.split("-", 1)
            try: return int(a) * 12 + int(b)
            except ValueError: return np.nan
        return np.nan
    comb["ht_in"] = comb["ht"].map(ht_to_in)
    cc = ["forty", "vertical", "broad_jump", "cone", "shuttle", "bench", "ht_in", "wt"]
    comb = comb[["pfr_id"] + cc]
    p = p.merge(comb, left_on="pfr_player_id", right_on="pfr_id", how="left")
    p["bmi"] = 703 * p["wt"] / (p["ht_in"] ** 2)
    p["speed_score"] = (p["wt"] * 200.0) / (p["forty"] ** 4)
    combine_cols = cc + ["bmi", "speed_score"]

    # --- group 3 college box (cfbfastR, norm_name) ---
    cf = pd.read_csv(REPO / "college_features.csv")
    cfb_cols = [c for c in cf.columns if c.startswith("cfb_") and c not in ("cfb_name", "cfb_team", "cfb_pos")]
    cfb_num = [c for c in cfb_cols if pd.api.types.is_numeric_dtype(cf[c])]
    cf = cf[["norm_name"] + cfb_num].drop_duplicates("norm_name")
    p = p.merge(cf, on="norm_name", how="left")

    # --- group 4 college PFF (position-specific, final season, norm_name) ---
    recv = _load_pff("receiving", PFF_RECV)
    rush = _load_pff("rushing", PFF_RUSH)
    pas = _load_pff("passing", PFF_PASS)
    # WR/TE <- receiving ; RB <- rushing (+ receiving) ; QB <- passing
    p = p.merge(recv, on="norm_name", how="left")
    p = p.merge(rush, on="norm_name", how="left")
    p = p.merge(pas, on="norm_name", how="left")
    pff_cols = [c for c in p.columns if c.startswith("pff_")]

    feature_cols = ["draft_pick", "draft_round", "log_pick", "age"] + combine_cols + cfb_num + pff_cols
    return p, dict(draft=["draft_pick", "draft_round", "log_pick"], combine=combine_cols,
                   cfb=cfb_num, pff=pff_cols, age=["age"]), feature_cols


def report(tag, feat, groups, feature_cols):
    print(f"\n=== {tag}: n={len(feat)} | feature cols={len(feature_cols)} ===")
    assert "hit" not in feature_cols and "best_finish" not in feature_cols, "LABEL LEAKED INTO FEATURES"
    for g, cols in groups.items():
        cov = feat[cols].notna().any(axis=1).mean() if cols else 0.0
        print(f"  group {g:7s}: {len(cols):2d} cols | any-present coverage {cov:5.1%}")
    # per-position combine + pff coverage (structural)
    for pos in SKILL:
        sub = feat[feat.position == pos]
        cmb = sub[groups["combine"]].notna().any(axis=1).mean()
        # position-appropriate pff block
        blk = ("pff_passing_" if pos == "QB" else "pff_rushing_" if pos == "RB" else "pff_receiving_")
        pffc = [c for c in groups["pff"] if c.startswith(blk)]
        pcov = sub[pffc].notna().any(axis=1).mean() if pffc else float("nan")
        print(f"    {pos}: combine {cmb:5.1%} | PFF({blk[4:-1]}) {pcov:5.1%}  n={len(sub)}")


def main():
    hit = pd.read_parquet(HERE / "panel_hit.parquet")
    scoring = pd.read_parquet(HERE / "panel_scoring.parquet")

    fh, groups, feat_cols = build_features(hit)
    fs, _, _ = build_features(scoring)

    print("=" * 64); print("PART B STRUCTURAL ASSERTS (no feature-vs-target)"); print("=" * 64)
    assert len(fh) == 712, "hit rows changed after feature join"
    assert len(fs) == 235, "scoring rows changed after feature join"
    report("HIT panel", fh, groups, feat_cols)
    report("SCORING", fs, groups, feat_cols)

    # dtype assert: all feature cols numeric
    nonnum = [c for c in feat_cols if not pd.api.types.is_numeric_dtype(fh[c])]
    assert not nonnum, f"non-numeric feature cols: {nonnum}"
    print("\n  dtype assert: all feature cols numeric — OK")

    fh.to_parquet(HERE / "feat_hit.parquet", index=False)
    fs.to_parquet(HERE / "feat_scoring.parquet", index=False)
    pd.Series(feat_cols).to_csv(HERE / "feature_cols.csv", index=False, header=["col"])
    import json
    (HERE / "feature_groups.json").write_text(json.dumps(groups, indent=2))
    print(f"\nwrote feat_hit.parquet ({len(fh)}x{len(feat_cols)}), feat_scoring.parquet, feature_groups.json")
    print("PART B: PASS — features assembled, blindness intact (no feature-vs-target computed).")


if __name__ == "__main__":
    main()
