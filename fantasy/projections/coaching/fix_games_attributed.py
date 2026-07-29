"""v3.2 PREFIT CORRECTION — recompute `n_games_attributed` in the canonical play-caller table.

DEFECT. The column was originally derived by WEEK ARITHMETIC
    n_games_attributed = min(week_end, team_games) - week_start + 1
which over-counts any segment spanning a bye: GB 2015 weeks 1-14 span 14 WEEKS but only 13 GAMES.
It affects exposure weights and reliability directly, so a known-wrong canonical column is not worth
preserving to retain a checksum. The checksum is an integrity tripwire, not the scientific object.

WHAT CHANGES. Only `n_games_attributed`, only on the 14 identified historical segment rows.
WHAT DOES NOT. Every sourced fact: caller identity, effective weeks, role, nominal OC, head coach,
source URL/date/publisher, confidence, ambiguity status, identity flags, notes, row count, row order.
Enforced by a strict diff allowlist that aborts on any other change.

HISTORICAL RULE (season <= 2025): distinct actual REG games inside [week_start, week_end], counted
from the PBP-derived weekly components using the SAME normalised team identifiers as
build_segment_offense.py. Weeks spanning a bye are not games.

PROSPECTIVE RULE (season 2026): games have not occurred, so actual counts do not exist. The
prospective count is the number of REG games SCHEDULED for that team inside the week range, taken
from the nflverse schedule (which carries unplayed 2026 fixtures). It is explicitly a scheduled
count, not an actual one, and is NOT set to zero merely because PBP is unavailable.
"""
import hashlib
import shutil
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CANON = DATA / "actual_play_caller.csv"
OLD_MD5 = "ac9883e98cdb1bd04a1c0978746cc023"
LAST_PLAYED = 2025

ALLOWED_CHANGED_COL = "n_games_attributed"


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def main():
    print("=" * 82)
    print("v3.2 PREFIT CORRECTION — n_games_attributed")
    print("=" * 82)

    before_md5 = md5(CANON)
    assert before_md5 == OLD_MD5, f"canonical table is not at the expected frozen md5: {before_md5}"
    print(f"  verified superseded md5 : {before_md5}")

    old = pd.read_csv(CANON)
    new = old.copy()

    wk = pd.read_csv(DATA / "weekly_offense_components.csv")          # PBP-derived, TEAM_CANON applied
    hcg = pd.read_csv(DATA / "head_coach_games.csv")                   # includes UNPLAYED 2026 fixtures

    ws = pd.to_numeric(old["week_start"], errors="coerce").fillna(1).astype(int)
    we = pd.to_numeric(old["week_end"], errors="coerce").fillna(99).astype(int)

    recomputed = []
    for i, r in old.iterrows():
        a, b = int(ws.iloc[i]), int(we.iloc[i])
        if pd.isna(r["person_id"]):
            recomputed.append(r[ALLOWED_CHANGED_COL])          # unresolved rows untouched
            continue
        if r["season"] <= LAST_PLAYED:
            w = wk[(wk.season == r["season"]) & (wk.team == r["team"])
                   & (wk.week >= a) & (wk.week <= b)]
            recomputed.append(float(w["games"].sum()))
        else:
            g = hcg[(hcg.season == r["season"]) & (hcg.team == r["team"])
                    & (hcg.week >= a) & (hcg.week <= b)]
            recomputed.append(float(g["game_id"].nunique()))   # PROSPECTIVE: scheduled games
    new[ALLOWED_CHANGED_COL] = recomputed

    # ---------------- strict diff allowlist ----------------
    assert list(old.columns) == list(new.columns), "column set/order changed"
    assert len(old) == len(new), "row count changed"
    changed_cols = []
    for c in old.columns:
        a_, b_ = old[c], new[c]
        same = (a_.isna() & b_.isna()) | (a_.astype(str) == b_.astype(str))
        if not same.all():
            changed_cols.append(c)
    print(f"  columns with any change : {changed_cols}")
    assert changed_cols == [ALLOWED_CHANGED_COL], \
        f"ALLOWLIST VIOLATION — unexpected columns changed: {set(changed_cols)-{ALLOWED_CHANGED_COL}}"

    d = old[ALLOWED_CHANGED_COL].fillna(-1) != new[ALLOWED_CHANGED_COL].fillna(-1)
    ch = old.loc[d, ["season", "team", "person_id", "week_start", "week_end"]].copy()
    ch["old_games"] = old.loc[d, ALLOWED_CHANGED_COL].values
    ch["new_games"] = new.loc[d, ALLOWED_CHANGED_COL].values
    ch["delta"] = ch["new_games"] - ch["old_games"]
    hist = ch[ch.season <= LAST_PLAYED]
    print(f"  rows changed            : {int(d.sum())} "
          f"({len(hist)} historical, {int(d.sum())-len(hist)} prospective/2026)")
    print()
    print(hist.to_string(index=False))

    assert len(hist) == 14, f"expected exactly 14 historical corrections, got {len(hist)}"
    assert set(hist.season.unique()) <= {2015, 2016, 2017}, "historical corrections outside 2015-2017"
    g = hist.groupby(["season", "team"])["delta"].agg(["sum", "size", "min", "max"])
    assert len(g) == 7, f"expected 7 affected team-seasons, got {len(g)}"
    assert (g["sum"] == 0).all(), "an affected team-season does not net to zero"
    assert ((g["size"] == 2) & (g["min"] == -1) & (g["max"] == 1)).all(), \
        "an affected team-season is not a clean +1/-1 pair"
    print("\n  allowlist + shape assertions: PASS (14 rows / 7 team-seasons / all +1,-1 pairs)")

    # ---------------- reconciliation tests ----------------
    res = new[new.person_id.notna()].copy()
    hres = res[res.season <= LAST_PLAYED]
    ts = hres.groupby(["season", "team"])[ALLOWED_CHANGED_COL].sum().reset_index(name="seg_sum")
    actual = wk.groupby(["season", "team"])["games"].sum().reset_index(name="team_games")
    rec = ts.merge(actual, on=["season", "team"], how="left")
    bad = rec[rec.seg_sum != rec.team_games]
    assert len(bad) == 0, f"segment sums != team games for {len(bad)} team-seasons"
    print(f"  segment sums == team games  : PASS ({len(rec)} resolved historical team-seasons)")

    ov = 0
    for (s_, t_), grp in res.groupby(["season", "team"]):
        iv = sorted(zip(pd.to_numeric(grp.week_start).fillna(1),
                        pd.to_numeric(grp.week_end).fillna(99)))
        for x, y in zip(iv, iv[1:]):
            if x[1] >= y[0]:
                ov += 1
    assert ov == 0, f"{ov} overlapping week ranges — a game could be assigned to two callers"
    print(f"  no overlapping ranges       : PASS")

    unassigned = 0
    for (s_, t_), grp in hres.groupby(["season", "team"]):
        weeks = set(wk[(wk.season == s_) & (wk.team == t_)].week)
        cov = set()
        for _, r in grp.iterrows():
            a, b = int(r.week_start), int(r.week_end if pd.notna(r.week_end) else 99)
            cov |= {w for w in weeks if a <= w <= b}
        unassigned += len(weeks - cov)
    assert unassigned == 0, f"{unassigned} played games inside resolved team-seasons are unassigned"
    print(f"  no unassigned game in range : PASS")

    # ---------------- write + re-freeze ----------------
    shutil.copy2(CANON, DATA / f"actual_play_caller.SUPERSEDED_{OLD_MD5[:8]}.csv")
    new.to_csv(CANON, index=False)
    after = md5(CANON)
    print(f"\n  superseded md5 : {OLD_MD5}")
    print(f"  NEW canonical md5 : {after}")
    print(f"  superseded copy retained at actual_play_caller.SUPERSEDED_{OLD_MD5[:8]}.csv")
    return after


if __name__ == "__main__":
    main()
