"""PHASE 1C — GAME-SHARE EXPOSURE for the cross-classified Arm 3 design matrix.

Repairs confirmed defect 2: `stage2_effects()` attached ONE primary caller per team-season with
weight 1.0, discarding the secondary caller from every one of the 18 sourced splits.

DESIGN — exposure is resolved at GAME level, then aggregated.
For each (season, team, week) we know the head coach (nflverse, game-by-game) and the actual
play-caller (canonical table week ranges). A team-season's design row therefore carries, for each
person, the share of that team-season's games in which they held the role:

    exposure(person, role, season, team) = games_in_that_role / total_games_in_team_season

so a caller responsible for 10 of 16 games receives 10/16.

HC == PC COLLAPSE (§4 identifiability). When the same person is head coach AND play-caller for a
given GAME, that game is a single "offensive lead" observation: it contributes to the HC block only
and is withheld from the PC block. The same person is therefore never counted twice for the same
game. Because the collapse is decided per GAME, a coach who takes over or gives up play-calling
midseason is handled naturally — his HC-only games and his HC+PC games are separated.

UNKNOWN CALLERS (frozen treatment). A game with no attributable play-caller contributes its HC
exposure normally and contributes NOTHING to the PC block. It is never assigned to a residual
"unknown" identity column, because an unknown-caller column would pool unrelated people into one
estimated effect. Unknown games therefore reduce a team-season's total PC exposure below 1.0, which
is the honest representation: we do not know who called them.

Row sums: HC exposure sums to 1.0 for every team-season with a known head coach. PC exposure sums to
(known-caller games / total games), which is 1.0 only when the whole season is resolved.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


def _pid(name):
    import re
    import unicodedata
    if not isinstance(name, str) or not name.strip():
        return None
    x = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    x = x.lower().replace(".", "").replace("'", "").replace("-", " ")
    x = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", x)
    return "_".join(x.split())


def game_level_identity(hc_games: pd.DataFrame, pc_table: pd.DataFrame) -> pd.DataFrame:
    """One row per (season, team, week): hc_person_id and pc_person_id (pc may be NaN)."""
    g = hc_games[["season", "team", "week", "game_id", "head_coach"]].dropna(subset=["head_coach"]).copy()
    g["hc_person_id"] = g["head_coach"].map(_pid)

    pc = pc_table[pc_table.person_id.notna()].copy()
    pc["week_start"] = pd.to_numeric(pc["week_start"], errors="coerce").fillna(1).astype(int)
    pc["week_end"] = pd.to_numeric(pc["week_end"], errors="coerce").fillna(99).astype(int)

    # object dtype on purpose: a float64 NaN column rejects string assignment in pandas >= 2.2
    g["pc_person_id"] = pd.Series([None] * len(g), index=g.index, dtype="object")
    for _, seg in pc.iterrows():
        m = ((g.season == seg.season) & (g.team == seg.team)
             & (g.week >= seg.week_start) & (g.week <= seg.week_end))
        g.loc[m, "pc_person_id"] = seg.person_id
    return g


def exposure_long(gl: pd.DataFrame) -> pd.DataFrame:
    """Long-format exposure: one row per (season, team, person_id, role) with share in [0,1]."""
    tot = gl.groupby(["season", "team"])["week"].size().rename("team_games")
    gl = gl.join(tot, on=["season", "team"])
    gl["same"] = (gl["hc_person_id"] == gl["pc_person_id"]) & gl["pc_person_id"].notna()

    hc = (gl.groupby(["season", "team", "hc_person_id", "team_games"]).size()
          .rename("games").reset_index().rename(columns={"hc_person_id": "person_id"}))
    hc["role"] = "hc"

    # PC block EXCLUDES games where the caller is also the head coach (collapse), and excludes
    # unknown-caller games entirely.
    pcg = gl[(~gl["same"]) & gl["pc_person_id"].notna()]
    pc = (pcg.groupby(["season", "team", "pc_person_id", "team_games"]).size()
          .rename("games").reset_index().rename(columns={"pc_person_id": "person_id"}))
    pc["role"] = "pc"

    out = pd.concat([hc, pc], ignore_index=True)
    out["exposure"] = out["games"] / out["team_games"]
    return out[["season", "team", "person_id", "role", "games", "team_games", "exposure"]]


# ------------------------------------------------------------------ SYNTHETIC TESTS
def _syn(rows):
    """rows: (week, hc, pc or None) -> game-level frame for one synthetic team-season."""
    return pd.DataFrame([dict(season=2000, team="SYN", week=w, game_id=f"g{w}",
                              hc_person_id=hc, pc_person_id=pc) for w, hc, pc in rows])


def run_synthetic_tests():
    print("\n--- PHASE 1C SYNTHETIC EXPOSURE TESTS ---")
    fails = []

    def check(label, gl, expect):
        e = exposure_long(gl)
        got = {(r.person_id, r.role): round(r.exposure, 6) for _, r in e.iterrows()}
        exp = {k: round(v, 6) for k, v in expect.items()}
        ok = got == exp
        hc_sum = round(e.loc[e.role == "hc", "exposure"].sum(), 6)
        if not ok:
            fails.append((label, exp, got))
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        print(f"        expected {exp}")
        if not ok:
            print(f"        got      {got}")
        print(f"        hc row-sum = {hc_sum}")
        return ok

    # 1. full-season HC who calls his own plays -> ONE offensive-lead effect, no PC duplicate
    check("1. full-season HC play-caller (collapse, no duplication)",
          _syn([(w, "reid", "reid") for w in range(1, 5)]),
          {("reid", "hc"): 1.0})

    # 2. full-season separate HC and OC caller
    check("2. full-season separate HC and OC caller",
          _syn([(w, "harbaugh", "mcdaniel") for w in range(1, 5)]),
          {("harbaugh", "hc"): 1.0, ("mcdaniel", "pc"): 1.0})

    # 3. midseason play-caller change, HC constant
    check("3. midseason caller change (2 of 4, then 2 of 4)",
          _syn([(1, "hc1", "pcA"), (2, "hc1", "pcA"), (3, "hc1", "pcB"), (4, "hc1", "pcB")]),
          {("hc1", "hc"): 1.0, ("pcA", "pc"): 0.5, ("pcB", "pc"): 0.5})

    # 4. midseason HC change, caller constant
    check("4. midseason HC change (3 of 4, then 1 of 4)",
          _syn([(1, "hcA", "pc1"), (2, "hcA", "pc1"), (3, "hcA", "pc1"), (4, "hcB", "pc1")]),
          {("hcA", "hc"): 0.75, ("hcB", "hc"): 0.25, ("pc1", "pc"): 1.0})

    # 5. simultaneous HC and caller change
    check("5. simultaneous HC + caller change",
          _syn([(1, "hcA", "pcA"), (2, "hcA", "pcA"), (3, "hcB", "pcB"), (4, "hcB", "pcB")]),
          {("hcA", "hc"): 0.5, ("hcB", "hc"): 0.5, ("pcA", "pc"): 0.5, ("pcB", "pc"): 0.5})

    # 6. unknown caller for part of the season -> PC exposure < 1, no 'unknown' column
    check("6. unknown caller for 2 of 4 games",
          _syn([(1, "hc1", "pc1"), (2, "hc1", "pc1"), (3, "hc1", None), (4, "hc1", None)]),
          {("hc1", "hc"): 1.0, ("pc1", "pc"): 0.5})

    # 7. HC becomes the caller midseason -> collapse applies ONLY to the games he called
    check("7. HC takes over play-calling at midseason",
          _syn([(1, "hc1", "pcX"), (2, "hc1", "pcX"), (3, "hc1", "hc1"), (4, "hc1", "hc1")]),
          {("hc1", "hc"): 1.0, ("pcX", "pc"): 0.5})

    print(f"\n  synthetic exposure tests: {7 - len(fails)}/7 passed")
    assert not fails, f"exposure test failures: {[f[0] for f in fails]}"
    return True


def build():
    print("=" * 82)
    print("PHASE 1C — GAME-SHARE EXPOSURE MATRIX")
    print("=" * 82)
    run_synthetic_tests()

    hcg = pd.read_csv(DATA / "head_coach_games.csv")
    pct = pd.read_csv(DATA / "actual_play_caller.csv")
    gl = game_level_identity(hcg, pct)
    gl.to_csv(DATA / "game_level_identity.csv", index=False)
    exp = exposure_long(gl)
    exp.to_csv(DATA / "coach_exposure.csv", index=False)

    print("\n--- REAL DATA ---")
    print(f"  game-level rows            : {len(gl):,}")
    print(f"  exposure rows              : {len(exp):,} "
          f"({exp.role.value_counts().to_dict()})")
    hc_sums = exp[exp.role == "hc"].groupby(["season", "team"])["exposure"].sum()
    print(f"  HC exposure sums to 1.0    : {int(np.isclose(hc_sums, 1.0).sum())}/{len(hc_sums)}")
    pc_sums = exp[exp.role == "pc"].groupby(["season", "team"])["exposure"].sum()
    print(f"  PC exposure <= 1.0 always  : {bool((pc_sums <= 1.0 + 1e-9).all())}")
    dup = exp.groupby(["season", "team", "person_id"]).size()
    both = int((dup > 1).sum())
    print(f"  person in BOTH blocks same team-season: {both} "
          f"(expected >0 only where he called part of the season)")

    print("\n  SANITY — a split team-season (2015 DET):")
    print(exp[(exp.season == 2015) & (exp.team == "DET")].to_string(index=False))
    print("\n  SANITY — an HC who calls his own plays (2026 LA):")
    print(exp[(exp.season == 2026) & (exp.team == "LA")].to_string(index=False))
    print("\n  SANITY — HC and caller distinct (2026 LAC):")
    print(exp[(exp.season == 2026) & (exp.team == "LAC")].to_string(index=False))
    print(f"\nwrote {DATA/'coach_exposure.csv'} + {DATA/'game_level_identity.csv'}")
    return exp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if a.test:
        run_synthetic_tests()
    elif a.build:
        build()
    else:
        raise SystemExit("pass --build or --test")
