"""Part B — feature matrix (5 groups) joined to the panel (BLIND build; NO feature-vs-target).

Groups (prereg §4), all point-in-time AT DRAFT:
  1 DRAFT CAPITAL  draft_pick(overall), draft_round, log_pick               [gsis]
  2 COMBINE        forty,vertical,broad_jump,cone,shuttle,bench,ht_in,wt,bmi,speed_score [pfr->gsis]
  5 AGE            age at draft                                              [gsis]
  3 COLLEGE BOX    cfb_* from college_features.csv                          [norm_name]
  4 COLLEGE PFF    position-specific grades from the LATEST COLLEGE SEASON STRICTLY BEFORE the
                   panel row's reference season                             [norm_name, POINT-IN-TIME]

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


# PFF college `position` codes that can plausibly be the same person as an NFL panel position.
# Used ONLY to disambiguate a same-name collision, never as a primary filter, so an unambiguous
# name keeps its row even when the college listing disagrees with the NFL listing.
PFF_POSITION_COMPAT = {"RB": {"HB", "RB", "FB"}, "WR": {"WR"}, "TE": {"TE"}, "QB": {"QB"}}

# The files each `_pff_long` call actually consumed, for provenance fingerprinting. Reset per build.
CONSUMED_PFF_FILES = []


def pff_provenance(files=None):
    """Fingerprint the PRIVATE PFF inputs without exposing any of their contents.

    Only the files actually CONSUMED by the last `build_features` are covered — not the whole local
    library, most of which this build never opens. The digest is one SHA-256 over, for each file in
    sorted repo-relative-path order, the path bytes then the file bytes, so it is stable across
    machines and changes if any consumed byte or the consumed SET changes.
    """
    import hashlib
    paths = sorted({Path(f) for f in (CONSUMED_PFF_FILES if files is None else files)},
                   key=lambda p: p.as_posix())
    h = hashlib.sha256()
    seasons, kinds = set(), set()
    for p in paths:
        rel = p.relative_to(PFF).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(p.read_bytes())
        h.update(b"\x00")
        stem = p.stem                                   # college_<kind>_summary_<year>
        parts = stem.split("_")
        seasons.add(int(parts[-1]))
        kinds.add("_".join(parts[1:-2]))
    return {"n_files": len(paths), "sha256": h.hexdigest(),
            "seasons": sorted(seasons), "kinds": sorted(kinds),
            "relative_paths": [p.relative_to(PFF).as_posix() for p in paths]}


def _pff_long(kind, cols):
    """EVERY PFF college row for `kind`, with the SOURCE SEASON RETAINED.

    This replaces a `groupby(norm_name).season.idxmax()` collapse that discarded the source season
    before the join. That collapse selected the LATEST season in 2014-2025 for a name and attached it
    to every panel row carrying that name, so a later college player contaminated an earlier NFL
    rookie (measured: 2014 Mike Evans took 2021 receiving; 2016 Michael Thomas took 2025; 2015 Matt
    Jones took 2025 receiving and rushing). Season is now carried through to `_pff_point_in_time`.
    """
    frames = []
    for yr in PFF_SEASONS:
        f = PFF / f"college_{yr}" / f"college_{kind}_summary_{yr}.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f)
        d["pff_season"] = yr
        frames.append(d)
        CONSUMED_PFF_FILES.append(f)
    if not frames:
        return pd.DataFrame(columns=["norm_name", "pff_season", "pff_player_id", "pff_position"])
    alld = pd.concat(frames, ignore_index=True)
    alld["norm_name"] = alld["player"].map(norm_name)
    keep = [c for c in cols if c in alld.columns]
    out = alld[["norm_name", "pff_season", "player_id", "position"] + keep].copy()
    out = out.rename(columns={"player_id": "pff_player_id", "position": "pff_position"})
    out["pff_game_count"] = pd.to_numeric(alld.get("player_game_count"), errors="coerce")
    return out.rename(columns={c: f"pff_{kind}_{c}" for c in keep})


def _pff_point_in_time(long, panel, kind, season_col):
    """Attach, per panel row, the LATEST PFF season STRICTLY BEFORE that row's reference season.

    The frozen selection rule, in order:
      1. eligible = PFF rows for the name with `pff_season < reference_season`. A row at or after the
         reference season is NEVER eligible — that is the leak this function exists to prevent.
      2. no eligible row            -> NULL (the panel row simply has no prior PFF season).
      3. one PFF identity           -> that identity's LATEST eligible season.
      4. several PFF identities     -> disambiguate, in this order:
           a. keep only position-compatible rows; if exactly one identity survives, use it;
           b. otherwise keep only rows at `reference_season - 1` (a prospect's final college season is
              almost always the season before entry); if exactly one identity survives, use it;
           c. otherwise NULL. Identity cannot be established, and guessing is what produced the leak.
      5. ties inside the chosen (identity, season) resolve deterministically: latest season, then
         most college games, then lowest PFF player id.

    Returns one row per panel row (or none), keyed by the panel index.
    """
    feat_cols = [c for c in long.columns if c.startswith(f"pff_{kind}_")]
    empty = pd.DataFrame(columns=["_panel_ix", f"pff_{kind}_source_season"] + feat_cols)
    if long.empty or not len(panel):
        return empty

    keys = panel[["norm_name", season_col]].copy()
    keys["_panel_ix"] = panel.index
    keys["_pos"] = panel["position"].astype(str) if "position" in panel.columns else ""
    m = keys.merge(long, on="norm_name", how="inner")
    m = m[m["pff_season"] < m[season_col]]
    if m.empty:
        return empty

    n_ids = m.groupby("_panel_ix")["pff_player_id"].transform("nunique")
    simple, multi = m[n_ids == 1], m[n_ids > 1]

    resolved = [simple]
    if not multi.empty:
        compat = multi["_pos"].map(lambda p: PFF_POSITION_COMPAT.get(p, set()))
        pos_ok = multi[[c in s for c, s in zip(multi["pff_position"].astype(str), compat)]]
        n_pos = pos_ok.groupby("_panel_ix")["pff_player_id"].transform("nunique") if len(pos_ok) \
            else pd.Series(dtype=int)
        by_pos = pos_ok[n_pos == 1] if len(pos_ok) else pos_ok
        resolved.append(by_pos)

        settled = set(by_pos["_panel_ix"])
        rest = multi[~multi["_panel_ix"].isin(settled)]
        if not rest.empty:
            prior = rest[rest["pff_season"] == rest[season_col] - 1]
            n_prior = prior.groupby("_panel_ix")["pff_player_id"].transform("nunique") if len(prior) \
                else pd.Series(dtype=int)
            by_prior = prior[n_prior == 1] if len(prior) else prior
            # keep that identity's full eligible history, not only the disambiguating season
            if len(by_prior):
                chosen = by_prior[["_panel_ix", "pff_player_id"]].drop_duplicates()
                resolved.append(rest.merge(chosen, on=["_panel_ix", "pff_player_id"], how="inner"))

    # `resolved` is empty when EVERY candidate was an unresolvable same-name collision. That is a
    # normal outcome (the row simply gets no PFF block), not an error — `pd.concat([])` raises.
    kept = [r for r in resolved if len(r)]
    if not kept:
        return empty
    m = pd.concat(kept, ignore_index=True)
    if m.empty:
        return empty

    # Deterministic order; `tail(1)` then takes latest season, then most games, then lowest PFF id.
    m = m.sort_values(["_panel_ix", "pff_season", "pff_game_count", "pff_player_id"],
                      ascending=[True, True, True, False], kind="mergesort")
    picked = m.groupby("_panel_ix", as_index=False).tail(1)
    picked = picked.rename(columns={"pff_season": f"pff_{kind}_source_season"})
    return picked[["_panel_ix", f"pff_{kind}_source_season"] + feat_cols]


SEASON_COL_CANDIDATES = ("entry_year", "season")


def _reference_season_col(panel):
    """The panel column holding the NFL season the features must PRECEDE. No silent fallback.

    Every caller must supply one. A missing column used to be impossible to notice because the PFF
    join ignored season entirely; it now fails closed, because a join with no reference season cannot
    be point-in-time.
    """
    for c in SEASON_COL_CANDIDATES:
        if c in panel.columns:
            return c
    raise ValueError(
        f"panel has no reference-season column; expected one of {SEASON_COL_CANDIDATES}. The PFF join "
        f"is point-in-time and cannot run without knowing the season it must precede.")


def build_features(panel):
    p = panel.copy()
    season_col = _reference_season_col(p)
    CONSUMED_PFF_FILES.clear()

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

    # --- group 4 college PFF (position-specific, LATEST ELIGIBLE PRIOR season, norm_name) ---
    # WR/TE <- receiving ; RB <- rushing (+ receiving) ; QB <- passing.
    # The join is POINT-IN-TIME: only PFF seasons strictly before the panel row's reference season
    # are eligible. See `_pff_point_in_time` for the full selection and disambiguation rule.
    for kind, cols in (("receiving", PFF_RECV), ("rushing", PFF_RUSH), ("passing", PFF_PASS)):
        sel = _pff_point_in_time(_pff_long(kind, cols), p, kind, season_col)
        sel = sel.set_index("_panel_ix")
        for c in sel.columns:
            p[c] = sel[c].reindex(p.index)
    source_cols = [f"pff_{k}_source_season" for k in ("receiving", "rushing", "passing")]
    pff_cols = [c for c in p.columns if c.startswith("pff_") and c not in source_cols]

    # Structural guarantee, asserted rather than assumed: no attached PFF season may reach the
    # reference season. This is the leak, made impossible to reintroduce silently.
    for sc in source_cols:
        late = p[sc].notna() & (p[sc] >= p[season_col])
        if bool(late.any()):
            raise AssertionError(
                f"POINT-IN-TIME VIOLATION: {int(late.sum())} row(s) carry {sc} >= {season_col}")

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
