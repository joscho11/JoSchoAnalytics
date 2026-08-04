"""RB SEASON-TOTAL half-PPR PROJECTION — BUILD under committed prereg
PREREG_rb_projection_2026-07-21.md.

Two models sharing one target (prereg §2), merged into one projection column:
  VETERAN  (is_rookie==0): the 32 season_dataset prior/bio/landing features + preseason depth rank.
  ROOKIE   (is_rookie==1): draft+age+combine+cfb+PFF from the FROZEN hit-model rookie matrix
           (RB slice, §3-named cols) + season_dataset landing-spot + preseason depth rank.

TARGET (prereg §1) = OBSERVED season-total half-PPR (fantasy_points + 0.5*receptions, REG, summed
from weekly stats) — NOT target_ppg*games (which filters games>=11 and would drop partial seasons).

MODES
  --assemble       build both matrices + the target/depth joins, run the pre-registered asserts,
                   write vet/rookie/2026 frames to the TEMP scratch dir. NO model fit.
  --walk-forward   read the scratch frames, run the §8 walk-forward (2021-2025) with nested-CV
                   selection over the frozen §7 slate, the gates-nothing Sleeper reference (§9), and
                   score 2026 for face validity. Prints everything; writes NOTHING to the repo.

Anti-peeking (prereg §7): model family + hyperparameters chosen SOLELY by inner leave-one-season-out
CV on the training seasons; the outer test season is never consulted for any selection decision.
Missing data (prereg §5): native NaN for CatBoost/LGBM/XGB; within-RB median-impute + missing flag
for the ElasticNet baseline. No row dropped for missingness.

Interpreter: AI_hedge_fund/.venv/Scripts/python.exe (repo .venv broken). rookie_ppg_model.pkl is
untouched. NO parquet / raw-PFF season table is written to the repo (PFF-derived matrices regenerate
in a temp scratch dir, like the hit-model build).
"""
import sys, os, argparse, json, shutil, subprocess, tempfile, warnings, time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent                       # fantasy/projections
REPO = HERE.parent.parent                                    # JoSchoAnalytics
SEAS = HERE.parent / "seasonal_projections"
ROOK = HERE.parent / "rookie"
HARNESS = ROOK / "harness"
sys.path.insert(0, str(SEAS))
from _utils import norm_name                                  # repo-consistent normalization
from rookie_deploy_recovery import recover_missing_deploy_profiles, assert_drafted_deploy_profiles

SCRATCH = Path(os.environ.get("RB_SCRATCH",
    r"C:/Users/josep/AppData/Local/Temp/claude/c--Users-josep-Desktop-random-stuff-cowork-OS/"
    r"a0db9953-ac7c-4009-99e9-0c070fb2e7da/scratchpad/rb_projection"))
SCRATCH.mkdir(parents=True, exist_ok=True)

SEED = 42
TEST_SEASONS = [2021, 2022, 2023, 2024, 2025]                # prereg §8 (Sleeper coverage begins 2021)
DEPLOY = 2026
MAXOBS = 2025                                                # last fully-observed NFL season
DEPTH = "depth_rank"

# --- VETERAN feature pool (prereg §3; all present in season_dataset) + preseason depth rank ---
VET_FEATS = ["prior_ppg", "prior_half_ppr", "prior_games", "ppg_2yr", "ppg_3yr", "ppg_trend",
             "career_high_ppg", "prior_snap_share_pg", "prior_targets_pg", "prior_carries_pg",
             "prior_receptions_pg", "prior_touches_pg", "prior_target_share", "prior_air_yards_share",
             "prior_adot", "prior_td_rate", "prior_yptarget", "prior_ypc", "prior_rec_epa",
             "prior_rush_epa", "age", "years_exp", "draft_round", "draft_pick", "prior_team_pass_rate",
             "prior_team_plays", "vacated_target_share", "vacated_rush_share", "coach_changed",
             "qb_changed", "prior_games_missed", "missed_prior_season"]
VET_ALL = list(VET_FEATS)          # AMENDMENT 1 (2026-07-21): depth_rank DROPPED from the feature pool.
                                   # FACTUAL CORRECTION 2026-07-26: Amendment 1's stated premise ("absent in
                                   # nflreadpy for 2025/2026") was FALSE — the data exists, under a new ESPN
                                   # schema this file's own filter silently dropped. The EXCLUSION still
                                   # stands, on the deploy-realism evidence (64% of the pooled gain is the
                                   # missingness channel; the only deploy-era fold regresses when honestly
                                   # re-timed). See PREREG_rb_projection_2026-07-21.md, Amendment 1 correction.
                                   # depth_rank is computed for coverage/disclosure only, never a feature.

# --- ROOKIE feature pool (prereg §3 RB-slice: the §3-named cols; excludes cfb id/metadata cols) ---
ROOK_DRAFT = ["draft_round", "draft_pick", "log_pick"]
ROOK_AGE = ["age"]
ROOK_COMBINE = ["forty", "vertical", "broad_jump", "cone", "shuttle", "bench", "ht_in", "wt",
                "bmi", "speed_score"]
ROOK_CFB = ["cfb_final_dom", "cfb_best_dom", "cfb_scrim_ypg", "cfb_rush_ypg", "cfb_rec_ypg", "cfb_ypc",
            "cfb_ypr", "cfb_career_scrim_yds", "cfb_career_scrim_td", "cfb_seasons", "cfb_breakout_class"]
ROOK_PFF = ["pff_rushing_grades_run", "pff_rushing_grades_offense", "pff_rushing_elusive_rating",
            "pff_rushing_breakaway_percent", "pff_rushing_elu_yco", "pff_rushing_avoided_tackles",
            "pff_rushing_first_downs", "pff_rushing_touchdowns", "pff_receiving_yprr",
            "pff_receiving_routes"]
ROOK_LAND = ["prior_team_pass_rate", "prior_team_plays", "vacated_target_share", "vacated_rush_share",
             "coach_changed", "qb_changed"]
FROZEN_JOIN = ROOK_COMBINE + ROOK_CFB + ROOK_PFF             # the cols sourced from the frozen matrix
ROOK_ALL = ROOK_DRAFT + ROOK_AGE + ROOK_COMBINE + ROOK_CFB + ROOK_PFF + ROOK_LAND   # depth_rank DROPPED (Amendment 1)

FAMILIES = ["catboost", "lightgbm", "xgboost", "elasticnet"]  # §7 slate (RF optional/comparison-only: omitted)


def pdf(x):
    try:
        return x.to_pandas()
    except AttributeError:
        return x


# ----------------------------------------------------------------------------- TARGET (prereg §1)
def season_total_target():
    """Per (player_id, season) OBSERVED season-total half-PPR (REG), summed from weekly stats.
    Repo formula (build_season_dataset.py:90 / assemble_panel.py:53): fantasy_points + 0.5*receptions."""
    import nflreadpy as nfl
    seasons = list(range(2014, MAXOBS + 1))
    try:
        ps = pdf(nfl.load_player_stats(seasons=seasons))
    except TypeError:
        ps = pdf(nfl.load_player_stats()); ps = ps[ps["season"].isin(seasons)]
    if "season_type" in ps.columns:
        ps = ps[ps["season_type"] == "REG"]
    ps["half_ppr"] = ps["fantasy_points"].fillna(0) + 0.5 * ps["receptions"].fillna(0)
    tgt = (ps.groupby(["player_id", "season"])["half_ppr"].sum()
             .reset_index().rename(columns={"half_ppr": "y"}))
    return tgt


# --------------------------------------------------------------------- PRESEASON DEPTH RANK (§3/§6a)
# nflverse changed depth-chart providers for 2025: <=2024 are weekly charts
# (season/club_code/week/game_type/position/depth_team), 2025+ are ESPN daily snapshots
# (dt/team/pos_abb/pos_slot/pos_rank) with NO season and NO position/depth_team column. The old
# single `position == "RB"` filter silently dropped 100% of 2025 (554k rows) and 2026 (372k rows).
# Both schemas are parsed here; the two-schema rule mirrors
# build_season_dataset.py::_load_qb1_week1. depth_rank remains DISCLOSURE-ONLY — it is in no
# feature pool (Amendment 1) and this parsing fix does not change any model or projection.
DEPTH_SRC = "source_pos_rank"       # provider-raw rank, preserved verbatim; new feed only
NEW_FEED_FIRST_SEASON = 2025        # first season on the ESPN daily-snapshot schema
NEW_FEED_MAX_TIER = 2               # canonical new-feed tiers are 1-2 only (see _depth_modern)


def _depth_legacy(seasons, position):
    """<=2024 weekly charts. Preseason rank = depth_team ('1'=starter) at the player's MIN REG
    week (season-open snapshot; point-in-time — contains no within-season-Y performance).
    This body is the pre-2026-07-26 logic verbatim; legacy output must not move."""
    import nflreadpy as nfl
    dc = pdf(nfl.load_depth_charts(seasons=list(seasons)))
    if "game_type" in dc.columns:
        dc = dc[dc["game_type"].astype(str).str.upper().isin(["REG", "R", ""]) | dc["game_type"].isna()]
    dc = dc[dc["position"].astype(str) == position].copy()
    dc["depth_num"] = pd.to_numeric(dc["depth_team"], errors="coerce")
    dc = dc.dropna(subset=["gsis_id", "week", "depth_num"])
    dc["week"] = pd.to_numeric(dc["week"], errors="coerce")
    idx = dc.groupby(["gsis_id", "season"])["week"].idxmin()   # season-open (earliest week) row
    out = dc.loc[idx, ["gsis_id", "season", "depth_num"]].rename(columns={"depth_num": DEPTH})
    out[DEPTH_SRC] = np.nan                                    # legacy feed has no provider rank
    return out.drop_duplicates(["gsis_id", "season"])


def _depth_modern(season, position):
    """2025+ ESPN daily snapshots -> one point-in-time row per (gsis_id, season).

    AS-OF RULE (deterministic; inherited from `build_season_dataset._load_qb1_week1`): of the many
    daily snapshots, take the LAST one strictly BEFORE the season's first REG gameday, so the row
    is pre-kickoff. For an unplayed season no snapshot is filtered out and the rule degenerates to
    "the most recent snapshot", which is still point-in-time.

    CANONICAL TIER: rank within (team, pos_slot), emitted ONLY for tiers 1..NEW_FEED_MAX_TIER.
    This is the translation established by the WR depth work: the provider's raw `pos_rank` is not
    comparable to legacy `depth_team`, and an uncapped July chart carries 90-man camp rosters,
    which would swing listed-coverage against the legacy seasons. Deeper players are therefore left
    UNLISTED rather than fabricated into a tier. The provider's raw rank is preserved verbatim in
    `source_pos_rank` for provenance."""
    import nflreadpy as nfl
    dc = pdf(nfl.load_depth_charts(seasons=[season]))
    if not len(dc) or "dt" not in dc.columns:
        return None
    dc = dc.copy()
    dc["dt"] = pd.to_datetime(dc["dt"], utc=True)
    sched = pdf(nfl.load_schedules([season]))
    reg = sched.loc[sched["game_type"] == "REG", "gameday"].dropna() if "game_type" in sched.columns \
        else pd.Series(dtype=object)
    if len(reg):
        dc = dc[dc["dt"] < pd.Timestamp(min(reg), tz="UTC")]   # strictly pre-kickoff
    if not len(dc):
        return None
    dc = dc[dc["dt"] == dc["dt"].max()].copy()                 # the deterministic as-of snapshot
    dc = dc[dc["pos_abb"].astype(str) == position].copy()
    dc["pos_rank"] = pd.to_numeric(dc["pos_rank"], errors="coerce")
    dc = dc.dropna(subset=["gsis_id", "team", "pos_slot", "pos_rank"])
    if not len(dc):
        return None
    dc = dc.sort_values(["team", "pos_slot", "pos_rank", "gsis_id"], kind="mergesort")
    dc[DEPTH] = dc.groupby(["team", "pos_slot"])["pos_rank"].rank(method="first")
    # a player listed in more than one slot keeps his best (lowest) tier
    dc = dc.sort_values([DEPTH, "pos_rank", "gsis_id"], kind="mergesort") \
           .drop_duplicates(["gsis_id"], keep="first")
    out = dc[dc[DEPTH] <= NEW_FEED_MAX_TIER].copy()
    out["season"] = season
    out = out.rename(columns={"pos_rank": DEPTH_SRC})
    return out[["gsis_id", "season", DEPTH, DEPTH_SRC]].drop_duplicates(["gsis_id", "season"])


def depth_rank_table(position="RB", seasons=None):
    """Per (gsis_id, season) preseason depth rank across BOTH provider schemas.
    Returns gsis_id, season (int64), depth_rank (int64), source_pos_rank (float; new feed only).

    NOT A COMPARABLE SERIES ACROSS THE 2024/2025 BOUNDARY. Legacy seasons emit whatever tiers the
    weekly chart carried (1-3 for RB, ~150 listed players per season); new-feed seasons emit tiers
    1-2 only (64 per season, 32 teams x 2). Listed-coverage therefore steps down at 2025 by
    construction. Any future consumer that wants a single cross-era series must handle that step
    explicitly — it is exactly the missingness channel that sank depth_rank as a feature."""
    seasons = list(seasons) if seasons is not None else list(range(2014, DEPLOY + 1))
    legacy = [s for s in seasons if s < NEW_FEED_FIRST_SEASON]
    modern = [s for s in seasons if s >= NEW_FEED_FIRST_SEASON]
    frames = [_depth_legacy(legacy, position)] if legacy else []
    for s in modern:
        f = _depth_modern(s, position)
        if f is not None and len(f):
            frames.append(f)
    if not frames:
        return pd.DataFrame(columns=["gsis_id", "season", DEPTH, DEPTH_SRC])
    out = pd.concat(frames, ignore_index=True)
    out["season"] = pd.to_numeric(out["season"], errors="coerce").astype("int64")
    out[DEPTH] = pd.to_numeric(out[DEPTH], errors="coerce").astype("int64")
    out[DEPTH_SRC] = pd.to_numeric(out[DEPTH_SRC], errors="coerce")
    return out.drop_duplicates(["gsis_id", "season"]).reset_index(drop=True)


# --------------------------------------------------- FROZEN ROOKIE MATRIX (regen in TEMP scratch)
def frozen_rb_matrix():
    """Regenerate the FROZEN hit-model rookie feature matrix in a temp dir (PFF-derived parquet never
    touches the repo), return the RB slice keyed by gsis_id + norm_name + position + entry_year."""
    scr = Path(tempfile.mkdtemp(prefix="rb_frozen_"))
    for f in ("assemble_panel.py", "assemble_features.py", "feature_groups.json", "feature_cols.csv"):
        shutil.copy2(HARNESS / f, scr / f)
    for script in ("assemble_panel.py", "assemble_features.py"):
        r = subprocess.run([sys.executable, str(scr / script)], cwd=scr, capture_output=True, text=True)
        tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-400:]
        print(f"    [{script}] {tail}")
        assert r.returncode == 0, f"{script} failed:\n{r.stderr[-1200:]}"
    fh = pd.read_parquet(scr / "feat_hit.parquet")
    fs = pd.read_parquet(scr / "feat_scoring.parquet")
    assert len(fh) == 712 and int(fh.hit.sum()) == 135, "frozen panel != 712/135"
    frz = pd.concat([fh, fs], ignore_index=True)
    frz = frz[frz["position"].astype(str) == "RB"].copy()
    keep = ["gsis_id", "norm_name", "position", "entry_year"] + FROZEN_JOIN
    keep = [c for c in keep if c in frz.columns]
    missing = [c for c in FROZEN_JOIN if c not in frz.columns]
    assert not missing, f"frozen matrix missing expected RB cols: {missing}"
    frz = frz[keep].copy()
    shutil.rmtree(scr, ignore_errors=True)
    return frz


# --------------------------------------------------------------------------------------- ASSEMBLE
def assemble():
    sd = pd.read_csv(SEAS / "season_dataset_2014_2026.csv")
    rb = sd[sd["position"] == "RB"].copy()
    rb["log_pick"] = np.log(rb["draft_pick"].clip(lower=1))

    # target join (§1): observed season total; <=2025 missing => 0 (rostered, never played); 2026 => NaN
    tgt = season_total_target()
    rb = rb.merge(tgt, on=["player_id", "season"], how="left")
    pre26 = rb["season"] <= MAXOBS
    rb.loc[pre26, "y"] = rb.loc[pre26, "y"].fillna(0.0)

    # preseason depth rank join
    depth = depth_rank_table()
    rb = rb.merge(depth, left_on=["player_id", "season"], right_on=["gsis_id", "season"], how="left")
    rb = rb.drop(columns=[c for c in ["gsis_id"] if c in rb.columns])

    # route (§2)
    vet = rb[rb["is_rookie"] == 0].copy()
    rook = rb[rb["is_rookie"] == 1].copy()

    # rookie: join FROZEN combine+cfb+pff by gsis, then name+position coalesce (2026 placeholder-gsis seam)
    frz = frozen_rb_matrix()
    frz_g = frz.drop(columns=["norm_name", "position", "entry_year"]).drop_duplicates("gsis_id")
    rook = rook.merge(frz_g, left_on="player_id", right_on="gsis_id", how="left")
    rook = rook.drop(columns=[c for c in ["gsis_id"] if c in rook.columns])
    # coalesce still-missing rows (2026 + unmatched) by (norm_name, position), skipping ambiguous keys
    need = rook[FROZEN_JOIN].isna().all(axis=1)
    frz_n = (frz.drop(columns=["gsis_id", "entry_year"])
                .drop_duplicates(subset=["norm_name", "position"], keep=False))
    if need.any():
        fill = rook.loc[need, ["norm_name", "position"]].merge(frz_n, on=["norm_name", "position"], how="left")
        fill.index = rook.loc[need].index
        for c in FROZEN_JOIN:
            rook.loc[need, c] = fill[c].values
    rook = recover_missing_deploy_profiles(rook, FROZEN_JOIN, "rushing", deploy_season=DEPLOY)
    assert_drafted_deploy_profiles(rook, FROZEN_JOIN, deploy_season=DEPLOY)

    return vet, rook, rb


# --------------------------------------------------------------------------- WALK-FORWARD FOLD GUARD
# 2026-08-03. What was here before, in this file and copy-pasted into the WR/TE/QB
# builders, was a TAUTOLOGY:
#       assert (tr.season < Y).all()          with   tr = df[df.season < Y]
#       a4 &= (vet[vet.season < Y].season < Y).all()
# i.e. filter a frame by a predicate and then test that same predicate on the
# result. It can never be False. Verified by injecting 50 season-Y rows into the
# pool: the expression stayed True and the builder printed "PASS".
#
# The replacement validates the fold objects that are actually handed to the model,
# at the construction boundary, against an expectation derived from the POOL's
# season universe rather than from the filter that built the train fold.

class FoldLeakError(AssertionError):
    """A walk-forward fold violates the temporal / disjointness contract."""


def build_fold(df, Y, y="y"):
    """The one place a walk-forward fold is constructed: train = seasons strictly
    before Y, test = exactly season Y, both with an observed target."""
    Y = int(Y)
    tr = df[df["season"] < Y].dropna(subset=[y])
    te = df[df["season"] == Y].dropna(subset=[y])
    return tr, te


def assert_walk_forward_fold(tr, te, Y, tag, pool=None, y="y", key=("player_id", "season")):
    """Validate ONE fold. Raises FoldLeakError; returns a summary dict."""
    Y = int(Y)
    tr_seasons = {int(s) for s in pd.unique(tr["season"])}
    te_seasons = {int(s) for s in pd.unique(te["season"])}

    # (1) row identity DISJOINTNESS — pandas index AND the (player, season) key.
    #     Checked first: it is the only check that survives a frame whose season
    #     labels themselves are wrong.
    idx_overlap = set(tr.index) & set(te.index)
    if idx_overlap:
        raise FoldLeakError(f"WALK-FORWARD LEAK ({tag}, {Y}): {len(idx_overlap)} row(s) in BOTH "
                            f"folds by index, e.g. {sorted(map(str, idx_overlap))[:5]}")
    kcols = [c for c in key if c in tr.columns and c in te.columns]
    if kcols:
        ktr = set(map(tuple, tr[kcols].to_numpy()))
        kte = set(map(tuple, te[kcols].to_numpy()))
        both = ktr & kte
        if both:
            raise FoldLeakError(f"WALK-FORWARD LEAK ({tag}, {Y}): {len(both)} {tuple(kcols)} key(s) "
                                f"in BOTH folds, e.g. {sorted(map(str, both))[:5]}")

    # (2) the test fold is EXACTLY the target season
    if te_seasons != {Y}:
        raise FoldLeakError(f"WALK-FORWARD ({tag}, {Y}): test fold seasons "
                            f"{sorted(te_seasons)} != exactly [{Y}]")

    # (3) the train fold is EXACTLY the pool's pre-Y season set (independent of the
    #     `< Y` filter: an injected/mis-filtered season-Y row shows up as a surplus)
    if pool is not None:
        expected = {int(s) for s in pd.unique(pool.dropna(subset=[y])["season"]) if int(s) < Y}
        if tr_seasons != expected:
            raise FoldLeakError(
                f"WALK-FORWARD ({tag}, {Y}): train seasons {sorted(tr_seasons)} != expected "
                f"{sorted(expected)} (surplus {sorted(tr_seasons - expected)}, "
                f"missing {sorted(expected - tr_seasons)})")

    # (4) strict temporal maximum
    if not tr_seasons:
        raise FoldLeakError(f"WALK-FORWARD ({tag}, {Y}): empty training fold")
    if max(tr_seasons) >= Y:
        raise FoldLeakError(f"WALK-FORWARD LEAK ({tag}, {Y}): max train season "
                            f"{max(tr_seasons)} is not strictly < {Y}")

    return {"season": Y, "n_train": len(tr), "n_test": len(te),
            "train_seasons": sorted(tr_seasons)}


def assert_walk_forward_folds(df, tag, seasons=TEST_SEASONS, y="y", min_train=1):
    """Construct and validate EVERY fold of the walk-forward. Folds with an empty
    train or test side are reported as unvalidated (never silently ignored); at
    least one fold must validate."""
    validated, empty = [], []
    for Y in seasons:
        tr, te = build_fold(df, Y, y=y)
        if len(tr) < min_train or len(te) == 0:
            empty.append(int(Y))
            continue
        validated.append(assert_walk_forward_fold(tr, te, Y, tag, pool=df, y=y))
    if not validated:
        raise FoldLeakError(f"WALK-FORWARD ({tag}): no fold could be validated "
                            f"(empty folds {empty})")
    return {"validated": validated, "unvalidated_empty": empty}


# ----------------------------------------------------------------------------------------- ASSERTS
def _mae(y, p): return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))
def _rmse(y, p): return float(np.sqrt(np.mean((np.asarray(y, float) - np.asarray(p, float)) ** 2)))
def _rank(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    if len(y) < 3 or np.nanstd(p) == 0: return float("nan")
    return float(spearmanr(y, p, nan_policy="omit").correlation)


def run_asserts(vet, rook):
    print("=" * 74); print("STEP 2 — PRE-REGISTERED ASSERTS (no model metric)"); print("=" * 74)
    ok = True

    # 1. routing exhaustive + mutually exclusive (§2): disjoint on (player_id, season) identity
    n_tot = int((vet.shape[0]) + (rook.shape[0]))
    key_v = set(map(tuple, vet[["player_id", "season"]].to_numpy()))
    key_r = set(map(tuple, rook[["player_id", "season"]].to_numpy()))
    disjoint = key_v.isdisjoint(key_r) and (len(key_v) + len(key_r) == len(key_v | key_r))
    excl = bool((vet["is_rookie"] == 0).all() and (rook["is_rookie"] == 1).all())
    a1 = disjoint and excl and (n_tot == len(vet) + len(rook))
    ok &= a1
    print(f"1. ROUTING partition: vet {len(vet)} + rookie {len(rook)} = {n_tot} | (player,season) disjoint "
          f"{disjoint} | is_rookie clean {excl}  -> {'PASS' if a1 else 'FAIL'}")

    # 2. <=Y-1 LAG / no-target-in-features (§4): target 'y' absent from feature pools; deferred talent/
    #    efficiency buckets absent; every veteran feature is prior_*/bio/draft/landing (point-in-time);
    #    depth_rank is the season-open snapshot (contains no within-season-Y outcome).
    talent_leak = [c for c in (VET_ALL + ROOK_ALL) if ("talent" in c or "efficiency" in c or c == "y")]
    prior_derived = {"ppg_2yr", "ppg_3yr", "ppg_trend", "career_high_ppg"}   # multi-year prior aggregates
    knowable = {"age", "years_exp", "draft_round", "draft_pick", "vacated_target_share",
                "vacated_rush_share", "coach_changed", "qb_changed", "missed_prior_season"}
    same_season_stat = [c for c in VET_FEATS if not (c.startswith("prior_") or c in prior_derived
                                                     or c in knowable)]
    # Amendment 1 stands: depth_rank (and its provider-raw provenance column) are computed for
    # disclosure only and must never appear in a feature pool.
    depth_leak = [c for c in (VET_ALL + ROOK_ALL)
                  if c in (DEPTH, DEPTH_SRC) or "depth_rank" in c or "depth_chart" in c
                  or "depth_team" in c]
    a2 = (not talent_leak) and (not same_season_stat) and (not depth_leak)
    ok &= a2
    print(f"2. <=Y-1 LAG + NO-DEPTH: target/talent/efficiency in features {talent_leak or 'none'} | "
          f"non-prior veteran stat cols {same_season_stat or 'none'} | "
          f"depth cols {depth_leak or 'none'}  -> {'PASS' if a2 else 'FAIL'}")

    # 3. SHUFFLED-YEAR leakage probe: a proof-model (native-NaN HGB) carries aligned prior signal on the
    #    veteran slice, and DESTROYS it when the target is shuffled within season. (Machinery, not a metric.)
    from sklearn.ensemble import HistGradientBoostingRegressor
    v = vet[vet["season"] <= MAXOBS].dropna(subset=["y"]).copy()
    feats_ok = [c for c in VET_ALL if v[c].notna().sum() >= 30 and v[c].nunique(dropna=True) >= 3]
    tr, te = v[v.season < 2024], v[v.season == 2024]
    m = HistGradientBoostingRegressor(random_state=SEED, max_iter=200)
    m.fit(tr[feats_ok].to_numpy(float), tr["y"].to_numpy(float))
    aligned = _rank(te["y"], m.predict(te[feats_ok].to_numpy(float)))
    rng = np.random.default_rng(SEED)
    trs = tr.copy(); trs["y"] = trs.groupby("season")["y"].transform(lambda s: rng.permutation(s.values))
    ms = HistGradientBoostingRegressor(random_state=SEED, max_iter=200)
    ms.fit(trs[feats_ok].to_numpy(float), trs["y"].to_numpy(float))
    shuffled = _rank(te["y"], ms.predict(te[feats_ok].to_numpy(float)))
    a3 = (aligned > 0.20) and (abs(shuffled) < 0.15)
    ok &= a3
    print(f"3. SHUFFLE-LEAK probe (veteran, test 2024): aligned rankcorr {aligned:+.3f} (>.20) | "
          f"within-season-shuffled {shuffled:+.3f} (~0)  -> {'PASS' if a3 else 'FAIL'}")

    # 4. WALK-FORWARD folds never train on their test season (§8). Real fold-boundary
    #    validation (exact season sets, strict temporal max, index/key disjointness):
    #    the old expression re-tested the filter that built the frame and could not fail.
    a4 = True
    fold_note = []
    for nm, pool in (("vet", vet), ("rook", rook)):
        try:
            rep = assert_walk_forward_folds(pool, nm)
            fold_note.append(f"{nm} {len(rep['validated'])}/{len(TEST_SEASONS)} folds"
                             + (f" (empty {rep['unvalidated_empty']})" if rep["unvalidated_empty"] else ""))
        except FoldLeakError as e:
            a4 = False
            fold_note.append(f"{nm} RAISED: {e}")
    ok &= a4
    print(f"4. WALK-FORWARD guard (exact train/test season sets, strict max, disjoint rows): "
          f"{' | '.join(fold_note)}  -> {'PASS' if a4 else 'FAIL'}")

    assert ok, "PRE-REGISTERED ASSERTS FAILED — STOP"
    print("\nSTEP 2 ASSERTS: PASS")
    return ok


def coverage_report(vet, rook, rb):
    print("\n--- coverage / structure ---")
    for name, df, feats in (("VETERAN", vet, VET_ALL), ("ROOKIE", rook, ROOK_ALL)):
        n = len(df); ntr = len(df[df.season.isin(TEST_SEASONS)]); n26 = len(df[df.season == DEPLOY])
        print(f"{name}: rows {n} | 2021-2025 {ntr} | 2026 {n26} | features {len(feats)}")
    print("\nRB rows / target coverage by season:")
    g = rb.groupby("season").apply(lambda d: pd.Series({
        "rows": len(d), "vet": int((d.is_rookie == 0).sum()), "rook": int((d.is_rookie == 1).sum()),
        "y_present": f"{d['y'].notna().mean()*100:.0f}%", "depth_present": f"{d[DEPTH].notna().mean()*100:.0f}%",
        "sleeper_present": f"{d['sleeper_pts_half_ppr'].notna().mean()*100:.0f}%"}), include_groups=False)
    print(g.to_string())
    print("\n2026 opportunity-feature coverage (provisional gap, prereg §6):")
    d26 = rb[rb.season == DEPLOY]
    for c in ["vacated_rush_share", "vacated_target_share", "prior_team_pass_rate", "coach_changed",
              "qb_changed", "adp_pos_rank", DEPTH]:
        if c in d26.columns:
            nz = f" | non-zero {100*(d26[c].fillna(0) != 0).mean():.0f}%" if c in ("coach_changed", "qb_changed") else ""
            print(f"  {c:22s}: present {100*d26[c].notna().mean():4.0f}%{nz}")


# ------------------------------------------------------------------------------- MODEL / SLATE (§7)
def _grid(family):
    if family == "catboost":
        return [dict(depth=d, learning_rate=lr, l2_leaf_reg=l2, iterations=it)
                for d in (4, 6) for lr in (0.03, 0.06) for l2 in (3, 6) for it in (400, 800)]
    if family == "lightgbm":
        return [dict(num_leaves=nl, learning_rate=lr, n_estimators=ne)
                for nl in (15, 31) for lr in (0.03, 0.06) for ne in (400, 800)]
    if family == "xgboost":
        return [dict(max_depth=md, learning_rate=lr, n_estimators=ne, reg_lambda=rl)
                for md in (4, 6) for lr in (0.03, 0.06) for ne in (400, 800) for rl in (1, 5)]
    if family == "elasticnet":
        return [dict(alpha=a, l1_ratio=l1) for a in (0.001, 0.01, 0.1) for l1 in (0.2, 0.5, 0.8)]
    raise ValueError(family)


def _prep_native(tr, te, feats):
    return tr[feats].to_numpy(float), te[feats].to_numpy(float)     # NaN preserved (§5 native-NaN)


def _prep_median_flag(tr, te, feats):                                # §5 ElasticNet: median + missing flag
    med = tr[feats].median(numeric_only=True)
    def go(df):
        X = df[feats].copy()
        flags = X.isna().astype(float); flags.columns = [c + "_isna" for c in feats]
        X = X.fillna(med).fillna(0.0)
        return pd.concat([X, flags], axis=1).to_numpy(float)
    return go(tr), go(te)


def _prep(family, tr, te, feats):
    return _prep_median_flag(tr, te, feats) if family == "elasticnet" else _prep_native(tr, te, feats)


def _make_model(family, params):
    if family == "catboost":
        from catboost import CatBoostRegressor
        return CatBoostRegressor(loss_function="RMSE", random_seed=SEED, verbose=0,
                                 allow_writing_files=False, thread_count=-1, **params)
    if family == "lightgbm":
        from lightgbm import LGBMRegressor
        return LGBMRegressor(objective="mae", random_state=SEED, verbose=-1, n_jobs=-1, **params)
    if family == "xgboost":
        from xgboost import XGBRegressor
        return XGBRegressor(objective="reg:squarederror", random_state=SEED, verbosity=0,
                            n_jobs=-1, **params)     # missing=NaN by default -> native-NaN routing
    if family == "elasticnet":
        from sklearn.linear_model import ElasticNet
        return ElasticNet(random_state=SEED, max_iter=8000, **params)
    raise ValueError(family)


def _fit_predict(family, params, Xtr, ytr, Xte):
    m = _make_model(family, params)
    m.fit(Xtr, ytr)
    return np.asarray(m.predict(Xte), float)


def nested_select(train_df, feats, y="y"):
    """Inner leave-one-season-out CV over TRAINING seasons only. Returns (family, params, inner_mae) for
    the single best config across the whole frozen slate, plus the per-family best table. Never sees the
    outer test season."""
    tdf = train_df.dropna(subset=[y]).copy()
    seasons = sorted(tdf.season.unique())
    all_res = []
    for family in FAMILIES:
        for params in _grid(family):
            maes = []
            for s in seasons:
                itr, iva = tdf[tdf.season != s], tdf[tdf.season == s]
                if len(itr) < 50 or len(iva) < 5:
                    continue
                Xtr, Xva = _prep(family, itr, iva, feats)
                p = _fit_predict(family, params, Xtr, itr[y].to_numpy(float), Xva)
                maes.append(_mae(iva[y], p))
            if maes:
                all_res.append((family, params, float(np.mean(maes))))
    all_res.sort(key=lambda r: r[2])
    per_family = {}
    for fam, pr, mae in all_res:
        if fam not in per_family or mae < per_family[fam][1]:
            per_family[fam] = (pr, mae)
    return all_res[0], per_family


def walk_forward(df, feats, tag):
    """Per prereg §8: for each Y in 2021-2025, inner-CV select on seasons<Y, fit on seasons<Y, predict Y."""
    rows, chosen = [], []
    for Y in TEST_SEASONS:
        tr, te = build_fold(df, Y)
        if len(tr) < 60 or len(te) == 0:
            continue
        assert_walk_forward_fold(tr, te, Y, tag, pool=df)   # raises FoldLeakError
        t0 = time.time()
        (fam, params, imae), per_family = nested_select(tr, feats)
        Xtr, Xte = _prep(fam, tr, te, feats)
        p = _fit_predict(fam, params, Xtr, tr["y"].to_numpy(float), Xte)
        rows.append(pd.DataFrame({"season": Y, "player_id": te["player_id"].values,
                                  "player": te["player"].values, "y": te["y"].values, "pred": p,
                                  "sleeper": te["sleeper_pts_half_ppr"].values, "model": fam}))
        pf = " ".join(f"{k}:{v[1]:.2f}" for k, v in sorted(per_family.items(), key=lambda x: x[1][1]))
        chosen.append((Y, fam, params, imae, len(tr), len(te)))
        print(f"  [{tag}] {Y}: model={fam} inner-MAE={imae:.3f} (per-fam {pf}) "
              f"train={len(tr)} test={len(te)} ({time.time()-t0:.0f}s)")
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["season", "player_id", "player", "y", "pred", "sleeper", "model"])
    return out, chosen


def fit_full_and_score(train_df, score_df, feats):
    """Fit on ALL training rows (<=MAXOBS) with the inner-CV-chosen config, score the frame (e.g. 2026)."""
    tr = train_df[train_df.season <= MAXOBS].dropna(subset=["y"])
    (fam, params, imae), _ = nested_select(tr, feats)
    Xtr, Xsc = _prep(fam, tr, score_df, feats)
    pred = _fit_predict(fam, params, Xtr, tr["y"].to_numpy(float), Xsc)
    return pred, fam, params, imae


def fit_final_model(train_df, feats):
    """Fit the deploy model on all training rows (<=MAXOBS) with the inner-CV-chosen config; return the
    fitted estimator + provenance so it can be persisted and re-scored (LightGBM deploy = native-NaN)."""
    tr = train_df[train_df.season <= MAXOBS].dropna(subset=["y"])
    (fam, params, imae), _ = nested_select(tr, feats)
    Xtr, _ = _prep(fam, tr, tr.head(1), feats)
    model = _make_model(fam, params)
    model.fit(Xtr, tr["y"].to_numpy(float))
    med = tr[feats].median(numeric_only=True) if fam == "elasticnet" else None
    bundle = {"model": model, "feature_cols": list(feats), "family": fam, "params": params,
              "inner_cv_mae": imae, "target": "season_total_half_ppr", "seed": SEED,
              "median_impute": (None if med is None else med.to_dict()),
              "note": "RB season-total half-PPR projection; deploy config chosen by inner LOSO CV (prereg §7)."}
    return bundle


# ----------------------------------------------------------------------------------------- METRICS
def metrics_block(df, label):
    m = df.dropna(subset=["y", "pred"])
    return dict(label=label, n=len(m), MAE=_mae(m.y, m.pred), RMSE=_rmse(m.y, m.pred), rho=_rank(m.y, m.pred))


def report_walkforward(merged):
    print("\n" + "=" * 74); print("STEP 3 — WALK-FORWARD RESULTS (MAE / RMSE / Spearman)"); print("=" * 74)
    def line(d): return f"  {d['label']:22s} n={d['n']:4d}  MAE {d['MAE']:6.2f}  RMSE {d['RMSE']:6.2f}  rho {d['rho']:+.3f}"
    print("\nPOOLED (2021-2025):")
    for lab, sub in (("merged", merged), ("veteran", merged[merged.grp == "vet"]),
                     ("rookie", merged[merged.grp == "rook"])):
        print(line(metrics_block(sub, lab)))
    print("\nPER FOLD (merged):")
    for Y in TEST_SEASONS:
        s = merged[merged.season == Y]
        if len(s): print(line(metrics_block(s, str(Y))))
    print("\nPER MODEL-FAMILY USED (merged rows scored by that family):")
    for fam in sorted(merged.model.dropna().unique()):
        print(line(metrics_block(merged[merged.model == fam], fam)))


def report_sleeper(merged):
    print("\n" + "=" * 74)
    print("STEP 3 — SLEEPER REFERENCE  (§9 SHOWN, NOT GATED — reference only, gates nothing)")
    print("=" * 74)
    both = merged.dropna(subset=["y", "pred", "sleeper"])
    print(f"rows with Sleeper present (2021-2025): {len(both)} of {len(merged)}")
    def line(lab, d): return f"  {lab:10s} n={d['n']:4d}  MAE {d['MAE']:6.2f}  RMSE {d['RMSE']:6.2f}  rho {d['rho']:+.3f}"
    print("\nON THE SAME ROWS (Sleeper-covered):")
    print(line("projection", metrics_block(both, "proj")))
    print(line("sleeper", dict(label="s", n=len(both), MAE=_mae(both.y, both.sleeper),
                               RMSE=_rmse(both.y, both.sleeper), rho=_rank(both.y, both.sleeper))))
    print("\n  (per prereg §9 this comparison is stored for interest; 'beating Sleeper' gates nothing.)")


def report_2026(vp, rp):
    print("\n" + "=" * 74); print("STEP 3 — 2026 PROJECTIONS (face-validity; not integrated)"); print("=" * 74)
    both = pd.concat([vp.assign(grp="vet"), rp.assign(grp="rook")], ignore_index=True)
    both = both.sort_values("proj_2026", ascending=False).reset_index(drop=True)
    show = both[["player", "position", "grp", "proj_2026", "sleeper_pts_half_ppr", DEPTH, "draft_pick"]].copy()
    show.columns = ["player", "pos", "grp", "proj", "sleeper", "depth", "pick"]
    print("\nTOP-15 projected RBs (2026):")
    print(show.head(15).to_string(index=False))
    print("\nROOKIE RBs (2026) sorted by projection:")
    rk = show[show.grp == "rook"].copy()
    print(rk.to_string(index=False))
    for nm in ("jeremiyah love", "ashton jeanty"):
        r = both.assign(nn=both.player.map(norm_name))
        r = r[r.nn == nm]
        if len(r):
            x = r.iloc[0]
            print(f"\n  ANCHOR {x['player']} ({x['position']}, {x['grp']}): 2026 proj = {x['proj_2026']:.1f} "
                  f"half-PPR | Sleeper {x['sleeper_pts_half_ppr']}")


# --------------------------------------------------------------------------------------------- MAIN
def do_assemble():
    print("=" * 74); print("RB PROJECTION BUILD — ASSEMBLE (prereg PREREG_rb_projection_2026-07-21.md)")
    print("=" * 74)
    vet, rook, rb = assemble()
    run_asserts(vet, rook)
    coverage_report(vet, rook, rb)
    vet.to_parquet(SCRATCH / "vet.parquet", index=False)
    rook.to_parquet(SCRATCH / "rook.parquet", index=False)
    print(f"\nwrote {SCRATCH/'vet.parquet'} ({len(vet)}) + {SCRATCH/'rook.parquet'} ({len(rook)}) [scratch only]")


def do_walk_forward():
    vet = pd.read_parquet(SCRATCH / "vet.parquet")
    rook = pd.read_parquet(SCRATCH / "rook.parquet")
    print("=" * 74); print("RB PROJECTION BUILD — WALK-FORWARD + SLEEPER + 2026"); print("=" * 74)
    print("\nVETERAN nested-CV walk-forward:")
    vout, vchosen = walk_forward(vet, VET_ALL, "vet")
    print("\nROOKIE nested-CV walk-forward:")
    rout, rchosen = walk_forward(rook, ROOK_ALL, "rook")
    merged = pd.concat([vout.assign(grp="vet"), rout.assign(grp="rook")], ignore_index=True)
    merged.to_parquet(SCRATCH / "walkforward_preds.parquet", index=False)
    report_walkforward(merged)
    report_sleeper(merged)

    # 2026 face validity
    print("\nfitting final models on all training data (<=2025) and scoring 2026...")
    v26 = vet[vet.season == DEPLOY].copy(); r26 = rook[rook.season == DEPLOY].copy()
    vpred, vfam, vpar, vimae = fit_full_and_score(vet, v26, VET_ALL)
    rpred, rfam, rpar, rimae = fit_full_and_score(rook, r26, ROOK_ALL)
    v26["proj_2026"] = np.clip(vpred, 0, None); r26["proj_2026"] = np.clip(rpred, 0, None)
    print(f"  veteran final: {vfam} {vpar} (inner-MAE {vimae:.3f})")
    print(f"  rookie  final: {rfam} {rpar} (inner-MAE {rimae:.3f})")
    pd.concat([v26.assign(grp="vet"), r26.assign(grp="rook")], ignore_index=True).to_parquet(
        SCRATCH / "proj_2026.parquet", index=False)
    report_2026(v26, r26)
    print("\n" + "=" * 74)
    print("STOP 2 (HARD) — readout complete. NO board integration performed. Awaiting Joseph.")
    print("=" * 74)


def _score_bundle(bundle, df):
    feats, fam = bundle["feature_cols"], bundle["family"]
    if fam == "elasticnet":
        med = pd.Series(bundle["median_impute"])
        X = df[feats].copy(); flags = X.isna().astype(float); flags.columns = [c + "_isna" for c in feats]
        Xn = pd.concat([X.fillna(med).fillna(0.0), flags], axis=1).to_numpy(float)
    else:
        Xn = df[feats].to_numpy(float)
    return np.clip(bundle["model"].predict(Xn), 0, None)


# repo-facing output dirs (derived artifacts only — NO parquet, NO raw-PFF season tables)
MODELS_DIR = HERE / "models"
RESULTS_DIR = HERE / "results"
ROOKIE_PPG_MD5 = "872467b2295fce27761f9e04da01b6e8"


def _md5(p):
    import hashlib
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def do_ship():
    import joblib
    print("=" * 74); print("RB PROJECTION BUILD — SHIP (final models + derived board artifacts)"); print("=" * 74)
    MODELS_DIR.mkdir(exist_ok=True); RESULTS_DIR.mkdir(exist_ok=True)
    vet = pd.read_parquet(SCRATCH / "vet.parquet"); rook = pd.read_parquet(SCRATCH / "rook.parquet")
    wf = pd.read_parquet(SCRATCH / "walkforward_preds.parquet")

    # 1. fit + persist final deploy models (inner-CV-chosen configs; §7)
    vb = fit_final_model(vet, VET_ALL); rb_ = fit_final_model(rook, ROOK_ALL)
    joblib.dump(vb, MODELS_DIR / "rb_veteran_model.pkl"); joblib.dump(rb_, MODELS_DIR / "rb_rookie_model.pkl")
    md5s = {"rb_veteran_model.pkl": _md5(MODELS_DIR / "rb_veteran_model.pkl"),
            "rb_rookie_model.pkl": _md5(MODELS_DIR / "rb_rookie_model.pkl")}
    print(f"  veteran deploy: {vb['family']} {vb['params']} (inner-MAE {vb['inner_cv_mae']:.3f})")
    print(f"  rookie  deploy: {rb_['family']} {rb_['params']} (inner-MAE {rb_['inner_cv_mae']:.3f})")

    # 2. score 2026 (deploy) -> merged RB projection column (veteran + rookie)
    v26 = vet[vet.season == DEPLOY].copy(); r26 = rook[rook.season == DEPLOY].copy()
    v26["projection"] = np.round(_score_bundle(vb, v26), 1); r26["projection"] = np.round(_score_bundle(rb_, r26), 1)
    merged = pd.concat([v26, r26], ignore_index=True)
    merged["sleeper"] = merged["sleeper_pts_half_ppr"]
    merged["diff"] = np.round(merged["projection"] - merged["sleeper"], 1)
    proj_cols = ["player_id", "player", "position", "team", "is_rookie", "draft_pick", "adp_pos_rank",
                 "projection", "sleeper", "diff"]
    proj26 = merged[proj_cols].sort_values("projection", ascending=False)
    proj26.to_csv(RESULTS_DIR / "rb_projection_2026.csv", index=False)   # full RB (veteran+rookie) surface

    # 3. rookie-board projection join file (classes 2024/2025 = walk-forward OOS; 2026 = deploy)
    wfr = wf[(wf.grp == "rook") & (wf.season.isin([2024, 2025]))].copy()
    wfr["projection"] = np.round(wfr["pred"], 1)
    wfr = wfr.rename(columns={"season": "entry_class"})[["player", "entry_class", "projection", "sleeper"]]
    r26b = r26.rename(columns={"season": "entry_class"})[["player", "entry_class", "projection",
                                                          "sleeper_pts_half_ppr"]].rename(
        columns={"sleeper_pts_half_ppr": "sleeper"})
    board_proj = pd.concat([wfr, r26b], ignore_index=True)
    board_proj["norm_name"] = board_proj["player"].map(norm_name)
    board_proj["position"] = "RB"
    board_proj["diff"] = np.round(board_proj["projection"] - board_proj["sleeper"], 1)
    board_proj = board_proj[["norm_name", "position", "entry_class", "projection", "sleeper", "diff"]]
    board_proj = board_proj.drop_duplicates(["norm_name", "position", "entry_class"])
    board_proj.to_csv(RESULTS_DIR / "rb_rookie_board_projection.csv", index=False)

    # 4. walk-forward predictions + Sleeper comparison (derived-only)
    wf_out = wf[["season", "grp", "player_id", "player", "y", "pred", "sleeper", "model"]].copy()
    wf_out["pred"] = np.round(wf_out["pred"], 1)
    wf_out.to_csv(RESULTS_DIR / "walkforward_predictions.csv", index=False)
    m = wf.dropna(subset=["y", "pred"])
    both = m.dropna(subset=["sleeper"])
    rowsm = []
    for lab, d in (("projection_all", m), ("projection_vs_sleeper_rows", both)):
        rowsm.append(dict(scope=lab, n=len(d), MAE=round(_mae(d.y, d.pred), 2),
                          RMSE=round(_rmse(d.y, d.pred), 2), spearman=round(_rank(d.y, d.pred), 3)))
    rowsm.append(dict(scope="sleeper_vs_actual", n=len(both), MAE=round(_mae(both.y, both.sleeper), 2),
                      RMSE=round(_rmse(both.y, both.sleeper), 2), spearman=round(_rank(both.y, both.sleeper), 3)))
    pd.DataFrame(rowsm).to_csv(RESULTS_DIR / "sleeper_comparison.csv", index=False)

    # 5. integrity asserts
    assert _md5(SEAS / "models" / "rookie_ppg_model.pkl") == ROOKIE_PPG_MD5, "rookie_ppg_model.pkl CHANGED"
    for f in list(MODELS_DIR.glob("*")) + list(RESULTS_DIR.glob("*")):
        assert f.suffix != ".parquet", f"parquet written to repo: {f}"
    print(f"\nmodel md5s: " + " | ".join(f"{k}={v}" for k, v in md5s.items()))
    print(f"wrote models/{{rb_veteran_model,rb_rookie_model}}.pkl + results/{{rb_projection_2026,"
          f"rb_rookie_board_projection,walkforward_predictions,sleeper_comparison}}.csv")
    print(f"rookie_ppg_model.pkl md5 UNCHANGED: {ROOKIE_PPG_MD5}")
    print(f"\n2026 rookie-board RB projections ({len(board_proj[board_proj.entry_class==2026])} in class 2026):")
    print(board_proj[board_proj.entry_class == 2026].sort_values("projection", ascending=False).to_string(index=False))
    print("SHIP ARTIFACTS WRITTEN (derived only; no parquet / no raw PFF in repo).")


def do_refresh_deploy():
    """Re-score the deploy season with the existing final models; never retrain or rewrite pkls."""
    import joblib
    print("=" * 74); print("RB DEPLOY REFRESH — existing models only (no retrain)"); print("=" * 74)
    vet = pd.read_parquet(SCRATCH / "vet.parquet"); rook = pd.read_parquet(SCRATCH / "rook.parquet")
    paths = [MODELS_DIR / "rb_veteran_model.pkl", MODELS_DIR / "rb_rookie_model.pkl"]
    before = {p.name: _md5(p) for p in paths}
    vb, rb_ = (joblib.load(p) for p in paths)
    v26 = vet[vet.season == DEPLOY].copy(); r26 = rook[rook.season == DEPLOY].copy()
    v26["projection"] = np.round(_score_bundle(vb, v26), 1)
    r26["projection"] = np.round(_score_bundle(rb_, r26), 1)
    merged = pd.concat([v26, r26], ignore_index=True)
    merged["sleeper"] = merged["sleeper_pts_half_ppr"]
    merged["diff"] = np.round(merged["projection"] - merged["sleeper"], 1)
    cols = ["player_id", "player", "position", "team", "is_rookie", "draft_pick", "adp_pos_rank",
            "projection", "sleeper", "diff"]
    merged[cols].sort_values("projection", ascending=False).to_csv(RESULTS_DIR / "rb_projection_2026.csv", index=False)

    board_path = RESULTS_DIR / "rb_rookie_board_projection.csv"
    prior = pd.read_csv(board_path)
    prior = prior[pd.to_numeric(prior["entry_class"], errors="coerce") != DEPLOY]
    r26b = r26.rename(columns={"season": "entry_class"})[["player", "entry_class", "projection",
                                                              "sleeper_pts_half_ppr"]].rename(
        columns={"sleeper_pts_half_ppr": "sleeper"})
    r26b["norm_name"] = r26b["player"].map(norm_name); r26b["position"] = "RB"
    r26b["diff"] = np.round(r26b["projection"] - r26b["sleeper"], 1)
    board = pd.concat([prior, r26b[["norm_name", "position", "entry_class", "projection", "sleeper", "diff"]]],
                      ignore_index=True).drop_duplicates(["norm_name", "position", "entry_class"], keep="last")
    board.to_csv(board_path, index=False)
    assert before == {p.name: _md5(p) for p in paths}, "deploy refresh changed a model pkl"
    print(f"refreshed {len(r26)} 2026 rookie rows; model pkls unchanged: {before}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--walk-forward", dest="wf", action="store_true")
    ap.add_argument("--ship", action="store_true")
    ap.add_argument("--refresh-deploy", action="store_true")
    a = ap.parse_args()
    if a.assemble:
        do_assemble()
    elif a.wf:
        do_walk_forward()
    elif a.ship:
        do_ship()
    elif a.refresh_deploy:
        do_refresh_deploy()
    else:
        raise SystemExit("pass --assemble, --walk-forward, --ship, or --refresh-deploy")


if __name__ == "__main__":
    main()
