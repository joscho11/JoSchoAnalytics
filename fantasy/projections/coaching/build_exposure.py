"""PHASE 1C (v2) — CALLER-FIRST game-share exposure for the cross-classified Arm 3 design.

SUPERSEDES the HC-first collapse, which was a verified design failure: it routed Mike McDaniel's
Miami 2022-2025 play-calling into the HEAD-COACH block, leaving him **0 caller-block prior games**
entering his 2026 Chargers play-caller assignment, and it fractured Sean McVay's caller identity
across two blocks at his OC->HC title change. Caller skill is the thing that must transfer between
teams and titles, so the retained identity on a collapsed game must be the CALLER.

TWO BLOCKS
  caller_effect
      Active for the ACTUAL play-caller on every resolved game, whatever his staff title. Portable:
      OC games, HC-who-calls games and any-other-title games accumulate under ONE person identity.
  noncalling_hc_context_effect
      Active for the head coach ONLY on games where a DISTINCT KNOWN person called plays. It is the
      contextual head-coach contribution to an offense delegated to someone else. It is NOT a
      universal head-coach effect and must never be read as applying to HC-called games.

IDENTIFIABILITY (§4). On a game where the head coach is also the caller, the head-coach and caller
contributions cannot be separately identified. That game is assigned to the portable caller /
offensive-lead effect, and contributes nothing to the HC-context block. No game ever activates both
blocks for the same person.

UNKNOWN-CALLER GAMES (v3.6 — NEUTRAL treatment; the earlier rule is WITHDRAWN). No pooled "unknown
person" identity is ever created. On an unknown-caller game **NEITHER identity block activates**:
the caller effect stays at the league prior AND the head coach receives no HC-context exposure. He
still accrues ordinary résumé/win/tenure history from the game.

The withdrawn rule granted the head coach HC-context on unknown games and called that conservative.
It is not: it assigns offensive residuals to a head coach with no evidence he delegated. Measured on
Andy Reid entering 2026, the old rule reported 245 "delegated" games of which only **5** were
verified delegated (Matt Nagy, KC 2017) and **240** were unknown-caller games from 1999-2013, all
before the attribution window opens. `caller_known_share` / `unknown_caller_share` are emitted so
the missing attribution stays visible.

ROW SUMS, reconciling per team-season. caller exposure = `caller_known_share` (1.0 only when a
team-season is fully resolved); HC-context exposure = the share of games with a known DISTINCT
caller; `unknown_caller_share` = 1 - caller_known_share.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

ROLE_CALLER = "caller"
ROLE_HC_CTX = "noncalling_hc_context"


def _pid(name):
    if not isinstance(name, str) or not name.strip():
        return None
    x = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    x = x.lower().replace(".", "").replace("'", "").replace("-", " ")
    x = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", x)
    return "_".join(x.split())


def game_level_identity(hc_games, pc_table):
    """One row per (season, team, week): hc_person_id and caller_person_id (caller may be None)."""
    g = hc_games[["season", "team", "week", "game_id", "head_coach"]] \
        .dropna(subset=["head_coach"]).copy()
    g["hc_person_id"] = g["head_coach"].map(_pid)

    pc = pc_table[pc_table.person_id.notna()].copy()
    pc["week_start"] = pd.to_numeric(pc["week_start"], errors="coerce").fillna(1).astype(int)
    pc["week_end"] = pd.to_numeric(pc["week_end"], errors="coerce").fillna(99).astype(int)

    g["caller_person_id"] = pd.Series([None] * len(g), index=g.index, dtype="object")
    for _, seg in pc.iterrows():
        m = ((g.season == seg.season) & (g.team == seg.team)
             & (g.week >= seg.week_start) & (g.week <= seg.week_end))
        g.loc[m, "caller_person_id"] = seg.person_id
    return g


def exposure_long(gl):
    """Caller-first exposure. One row per (season, team, person_id, role)."""
    tot = gl.groupby(["season", "team"]).size().rename("team_games")
    gl = gl.join(tot, on=["season", "team"])
    known = gl["caller_person_id"].notna()
    same = known & (gl["hc_person_id"] == gl["caller_person_id"])

    # CALLER block — every resolved game, regardless of the person's title
    cal = (gl[known].groupby(["season", "team", "caller_person_id", "team_games"]).size()
           .rename("games").reset_index().rename(columns={"caller_person_id": "person_id"}))
    cal["role"] = ROLE_CALLER

    # NON-CALLING HC CONTEXT — HC only where a DISTINCT KNOWN person called.
    #
    # v3.6: the old rule was `ctx_mask = ~same`, which was WRONG. `same` is False both when a
    # distinct known person called AND when the caller is simply unknown, so every unknown-caller
    # game was credited to the head coach's "delegated offense" effect. It was labelled
    # conservative; it is not. It assigns offensive residuals to the HC without any evidence that
    # he delegated -- or that he didn't call the plays himself.
    #
    # Measured damage: Andy Reid entering 2026 showed hc_context = 245, of which only **5** were
    # verified delegated games (Matt Nagy, 2017). The other **240** were unknown-caller games, all
    # from 1999-2013, i.e. entirely before the attribution window opens in 2014.
    #
    # Neutral treatment: an unknown-caller game activates NEITHER identity block. The head coach
    # still accrues ordinary résumé/win/tenure history from it; he simply gets no offensive
    # identity effect. `unknown_caller_share` keeps the missing attribution visible.
    ctx_mask = known & (gl["hc_person_id"] != gl["caller_person_id"])
    ctx = (gl[ctx_mask].groupby(["season", "team", "hc_person_id", "team_games"]).size()
           .rename("games").reset_index().rename(columns={"hc_person_id": "person_id"}))
    ctx["role"] = ROLE_HC_CTX

    out = pd.concat([cal, ctx], ignore_index=True)
    out["exposure"] = out["games"] / out["team_games"]
    return out[["season", "team", "person_id", "role", "games", "team_games", "exposure"]]


def caller_known_share(gl):
    """Per team-season: known / unknown / distinct-caller shares. These must reconcile to 1.0.

    Emitted so that missing attribution stays VISIBLE rather than being silently absorbed into the
    head-coach block (which is what the pre-v3.6 rule did).
    """
    g = gl.copy()
    g["_known"] = g.caller_person_id.notna()
    g["_same"] = g._known & (g.hc_person_id == g.caller_person_id)
    g["_dist"] = g._known & (g.hc_person_id != g.caller_person_id)
    t = g.groupby(["season", "team"]).agg(
        team_games=("week", "size"),
        known=("_known", "sum"), self_called=("_same", "sum"),
        distinct_caller=("_dist", "sum")).reset_index()
    t["unknown"] = t.team_games - t.known
    t["caller_known_share"] = t.known / t.team_games
    t["unknown_caller_share"] = t.unknown / t.team_games
    t["hc_context_share"] = t.distinct_caller / t.team_games
    assert (t.known + t.unknown == t.team_games).all()
    assert (t.self_called + t.distinct_caller == t.known).all()
    return t


# ------------------------------------------------------------------ preseason staff snapshot
def preseason_snapshot(gl):
    """Identities knowable at the season-Y projection cutoff, plus feature-eligible change flags.

    TIMING (prereg v3.3). A season-Y preseason feature may use only who is EXPECTED to open Y and
    what happened in completed seasons. It may NOT use anything learned during Y: whether a change
    eventually occurs, the eventual primary caller by games, or an eventual game-share blend. Those
    are historical attribution metadata and become usable only when Y becomes training data for Y+1.
    """
    gl = gl.sort_values(["season", "team", "week"])
    rows = []
    for (s, t), g in gl.groupby(["season", "team"]):
        opener = g.iloc[0]
        closer = g.iloc[-1]
        n_call = g["caller_person_id"].nunique(dropna=True)
        n_hc = g["hc_person_id"].nunique(dropna=True)
        prim = (g["caller_person_id"].value_counts().idxmax()
                if g["caller_person_id"].notna().any() else None)
        rows.append(dict(
            season=s, team=t,
            opening_caller_id=opener["caller_person_id"], opening_hc_id=opener["hc_person_id"],
            closing_caller_id=closer["caller_person_id"], closing_hc_id=closer["hc_person_id"],
            # HISTORICAL-ONLY (never a season-Y preseason feature)
            historical_primary_caller_id=prim,
            pc_within_season_change=int(n_call > 1),
            hc_within_season_change=int(n_hc > 1)))
    snap = pd.DataFrame(rows).sort_values(["team", "season"])

    # feature-eligible: opening caller of Y vs the caller who ENDED Y-1
    snap["prev_closing_caller_id"] = snap.groupby("team")["closing_caller_id"].shift(1)
    snap["prev_closing_hc_id"] = snap.groupby("team")["closing_hc_id"].shift(1)
    snap["pc_changed_entering"] = np.where(
        snap.opening_caller_id.isna() | snap.prev_closing_caller_id.isna(), np.nan,
        (snap.opening_caller_id != snap.prev_closing_caller_id).astype(float))
    snap["hc_changed_entering"] = np.where(
        snap.opening_hc_id.isna() | snap.prev_closing_hc_id.isna(), np.nan,
        (snap.opening_hc_id != snap.prev_closing_hc_id).astype(float))
    # lagged historical metadata IS eligible for season Y
    snap["prior_season_pc_changed_within"] = snap.groupby("team")["pc_within_season_change"].shift(1)
    snap["prior_season_hc_changed_within"] = snap.groupby("team")["hc_within_season_change"].shift(1)
    return snap.sort_values(["season", "team"]).reset_index(drop=True)


# ================================================================== TESTS
def _syn(rows, season=2000, team="SYN"):
    return pd.DataFrame([dict(season=season, team=team, week=w, game_id=f"g{season}{w}",
                              hc_person_id=hc, caller_person_id=c) for w, hc, c in rows])


def run_structural_tests():
    print("\n--- STRUCTURAL EXPOSURE TESTS (caller-first) ---")
    fails = []

    def check(label, gl, expect):
        e = exposure_long(gl)
        got = {(r.person_id, r.role): round(r.exposure, 6) for _, r in e.iterrows()}
        exp = {k: round(v, 6) for k, v in expect.items()}
        ok = got == exp
        if not ok:
            fails.append((label, exp, got))
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            print(f"        expected {exp}\n        got      {got}")

    C, H = ROLE_CALLER, ROLE_HC_CTX
    check("1. full-season HC who calls -> CALLER only, no HC-context",
          _syn([(w, "reid", "reid") for w in range(1, 5)]),
          {("reid", C): 1.0})
    check("2. separate HC and OC caller",
          _syn([(w, "harbaugh", "mcdaniel") for w in range(1, 5)]),
          {("mcdaniel", C): 1.0, ("harbaugh", H): 1.0})
    check("3. midseason caller change, HC constant",
          _syn([(1, "hc1", "pcA"), (2, "hc1", "pcA"), (3, "hc1", "pcB"), (4, "hc1", "pcB")]),
          {("pcA", C): 0.5, ("pcB", C): 0.5, ("hc1", H): 1.0})
    check("4. midseason HC change, caller constant",
          _syn([(1, "hcA", "pc1"), (2, "hcA", "pc1"), (3, "hcA", "pc1"), (4, "hcB", "pc1")]),
          {("pc1", C): 1.0, ("hcA", H): 0.75, ("hcB", H): 0.25})
    check("5. simultaneous HC + caller change",
          _syn([(1, "hcA", "pcA"), (2, "hcA", "pcA"), (3, "hcB", "pcB"), (4, "hcB", "pcB")]),
          {("pcA", C): 0.5, ("pcB", C): 0.5, ("hcA", H): 0.5, ("hcB", H): 0.5})
    # v3.6: the old expectation here was `("hc1", H): 1.0` -- HC-context RETAINED on unknown-caller
    # games. That rule is WITHDRAWN. It credited the head coach with a delegated-offense effect on
    # games where nobody knows who called plays. Unknown games now activate NEITHER identity block.
    check("6. unknown caller 2 of 4 -> caller 0.5, HC-context 0.5, unknown games attributed to "
          "NEITHER block",
          _syn([(1, "hc1", "pc1"), (2, "hc1", "pc1"), (3, "hc1", None), (4, "hc1", None)]),
          {("pc1", C): 0.5, ("hc1", H): 0.5})
    check("7. HC takes over calling midseason -> HC gets caller 0.5 AND context 0.5, never both "
          "on the same game",
          _syn([(1, "hc1", "pcX"), (2, "hc1", "pcX"), (3, "hc1", "hc1"), (4, "hc1", "hc1")]),
          {("pcX", C): 0.5, ("hc1", C): 0.5, ("hc1", H): 0.5})
    print(f"\n  structural tests: {7 - len(fails)}/7 passed")
    assert not fails, f"structural failures: {[f[0] for f in fails]}"


def run_timing_test():
    print("\n--- TIMING / LEAKAGE TEST ---")
    gl = pd.concat([
        _syn([(w, "hc1", "callerA") for w in range(1, 5)], season=2001),
        _syn([(1, "hc1", "callerA"), (2, "hc1", "callerA"),
              (3, "hc1", "callerB"), (4, "hc1", "callerB")], season=2002),
        _syn([(w, "hc1", "callerB") for w in range(1, 5)], season=2003)], ignore_index=True)
    snap = preseason_snapshot(gl)
    y2 = snap[snap.season == 2002].iloc[0]
    y3 = snap[snap.season == 2003].iloc[0]
    ok = True
    ok &= (y2.opening_caller_id == "callerA")
    print(f"  {'PASS' if y2.opening_caller_id=='callerA' else 'FAIL'}  2002 preseason routes "
          f"entirely through the OPENING caller (callerA), not the eventual blend")
    ok &= (y2.pc_changed_entering == 0.0)
    print(f"  {'PASS' if y2.pc_changed_entering==0.0 else 'FAIL'}  2002 pc_changed_entering = 0 "
          f"(callerA also ended 2001) — the midseason switch to callerB is NOT visible")
    ok &= (pd.isna(y2.prior_season_pc_changed_within) or y2.prior_season_pc_changed_within == 0.0)
    print(f"  {'PASS' if (pd.isna(y2.prior_season_pc_changed_within) or y2.prior_season_pc_changed_within==0.0) else 'FAIL'}"
          f"  2002 carries no within-season-change outcome for its own season")
    ok &= (y3.prior_season_pc_changed_within == 1.0)
    print(f"  {'PASS' if y3.prior_season_pc_changed_within==1.0 else 'FAIL'}  2003 MAY use the "
          f"completed 2002 transition (prior_season_pc_changed_within = 1)")
    ok &= (y3.pc_changed_entering == 0.0)
    print(f"  {'PASS' if y3.pc_changed_entering==0.0 else 'FAIL'}  2003 pc_changed_entering = 0 "
          f"(callerB ended 2002 and opens 2003)")
    assert ok, "timing/leakage test failed"


def run_routing_tests(exp, snap):
    print("\n--- CENTRAL ROUTING TESTS (real data) ---")
    ok = True

    md = exp[(exp.person_id == "mike_mcdaniel") & (exp.role == ROLE_CALLER)]
    mia = md[(md.season.between(2022, 2025)) & (md.team == "MIA")]
    prior = int(mia.games.sum())
    a = prior == 68
    ok &= a
    print(f"  {'PASS' if a else 'FAIL'}  McDaniel MIA 2022-2025 games (called while HC) land in the "
          f"CALLER block: {prior} games")
    lac = md[(md.season == 2026) & (md.team == "LAC")]
    b = len(lac) == 1 and float(lac.iloc[0].exposure) == 1.0
    ok &= b
    print(f"  {'PASS' if b else 'FAIL'}  McDaniel is the 2026 LAC caller at exposure "
          f"{float(lac.iloc[0].exposure) if len(lac) else 'MISSING'}")
    c = prior > 0
    ok &= c
    print(f"  {'PASS' if c else 'FAIL'}  entering 2026 his caller prior-games count INCLUDES Miami "
          f"({prior} > 0) — this was 0 under the HC-first collapse")
    hb = exp[(exp.person_id == "jim_harbaugh") & (exp.season == 2026) & (exp.team == "LAC")]
    d = len(hb) == 1 and hb.iloc[0].role == ROLE_HC_CTX
    ok &= d
    print(f"  {'PASS' if d else 'FAIL'}  Harbaugh receives ONLY non-calling-HC context for 2026 LAC")

    mv = exp[exp.person_id == "sean_mcvay"]
    mvc = mv[mv.role == ROLE_CALLER]
    was = int(mvc[(mvc.team == "WAS")].games.sum())
    ram = int(mvc[(mvc.team == "LA") & (mvc.season < 2026)].games.sum())
    e = was > 0 and ram > 0
    ok &= e
    print(f"  {'PASS' if e else 'FAIL'}  McVay WAS-as-OC ({was}) and LA-as-HC ({ram}) games "
          f"accumulate under ONE caller identity = {was + ram} prior games")
    f = len(mv[(mv.role == ROLE_HC_CTX)]) == 0
    ok &= f
    print(f"  {'PASS' if f else 'FAIL'}  McVay never appears in the HC-context block "
          f"({len(mv[mv.role == ROLE_HC_CTX])} rows) — he calls his own plays")

    lar = snap[(snap.season == 2026) & (snap.team == "LA")].iloc[0]
    lch = snap[(snap.season == 2026) & (snap.team == "LAC")].iloc[0]
    g = lar.pc_changed_entering == 0.0 and lch.pc_changed_entering == 1.0
    ok &= g
    print(f"  {'PASS' if g else 'FAIL'}  2026 preseason: LA pc_changed_entering="
          f"{lar.pc_changed_entering}, LAC={lch.pc_changed_entering}")
    assert ok, "central routing tests failed"


def build():
    print("=" * 84)
    print("PHASE 1C (v2) — CALLER-FIRST EXPOSURE")
    print("=" * 84)
    run_structural_tests()
    run_timing_test()

    hcg = pd.read_csv(DATA / "head_coach_games.csv")
    pct = pd.read_csv(DATA / "actual_play_caller.csv")
    gl = game_level_identity(hcg, pct)
    exp = exposure_long(gl)
    snap = preseason_snapshot(gl)
    cks = caller_known_share(gl)

    gl.to_csv(DATA / "game_level_identity.csv", index=False)
    exp.to_csv(DATA / "coach_exposure.csv", index=False)
    # NOT written here. Since v3.5 `preseason_staff_snapshot.csv` is the POINT-IN-TIME artifact
    # owned by build_preseason_snapshot.py, which gates every identity on pre-cutoff evidence.
    # This module's `snap` is the RETROSPECTIVE frame; writing it to the snapshot path silently
    # replaced the eligibility-gated artifact with retrospective identities -- the same
    # two-writers-one-file failure that hit source_ledger.csv.
    #
    # `retrospective_staff_transitions.csv` is ALSO not written here: build_preseason_snapshot.py
    # is its sole writer. `snap` is retained in memory for the routing tests only.
    #
    # OWNERSHIP (asserted by tests/test_artifact_ownership.py):
    #   build_exposure.py            -> game_level_identity.csv, coach_exposure.csv,
    #                                   caller_known_share.csv
    #   build_preseason_snapshot.py  -> retrospective_staff_transitions.csv,
    #                                   preseason_staff_snapshot.csv, preseason_evidence_ledger.csv
    cks.to_csv(DATA / "caller_known_share.csv", index=False)

    run_routing_tests(exp, snap)

    print("\n--- INVARIANTS ---")
    cal = exp[exp.role == ROLE_CALLER].groupby(["season", "team"])["exposure"].sum()
    ref = cks.set_index(["season", "team"])["caller_known_share"]
    aligned = cal.reindex(ref.index).fillna(0.0)
    print(f"  caller exposure == caller_known_share : "
          f"{int(np.isclose(aligned, ref).sum())}/{len(ref)}")
    dbl = gl[gl.caller_person_id.notna() & (gl.hc_person_id == gl.caller_person_id)]
    print(f"  games where HC==caller (collapsed)    : {len(dbl):,}")
    print(f"  exposure rows                         : {len(exp):,} "
          f"{exp.role.value_counts().to_dict()}")
    print("\nwrote game_level_identity.csv, coach_exposure.csv, caller_known_share.csv")
    return exp


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    if a.test:
        run_structural_tests(); run_timing_test()
    elif a.build:
        build()
    else:
        raise SystemExit("pass --build or --test")
