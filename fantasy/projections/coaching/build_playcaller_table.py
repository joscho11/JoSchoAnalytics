"""ACTUAL-PLAY-CALLER TABLE + COVERAGE REPORT.

Assembles `playcaller_sources.py` into the schema the amended prereg requires, one row per
(season, team, effective week range):

  season, team, person_id, actual_play_caller, play_caller_role, week_start, week_end,
  n_games_attributed, nominal_oc, head_coach, source_url, source_date, confidence, ambiguity_status

DESIGN RULES (all from the amended prereg §1):
  * person_id is a STABLE identity across job titles and teams. History belongs to the FUNCTION the
    person performed, not the title they held -- so Mike McDaniel's Miami head-coach play-calling
    seasons and his Chargers coordinator season carry the SAME person_id.
  * play_caller_role is DERIVED by comparing the play-caller against the authoritative nflverse
    head-coach table. Source role labels are never trusted and every disagreement is reported.
  * Nominal OC is carried as staff-continuity METADATA only. It is never promoted to play-caller.
  * Unknown/ambiguous/conflicting -> the row is emitted with actual_play_caller = NA so downstream
    routes it to the league prior, zero reliability, no_prior_history = 1.
"""
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
sys.path.insert(0, str(HERE))
import playcaller_sources as SRC   # noqa: E402

PANEL_SEASONS = list(range(2014, 2027))
OUTER_SEASONS = list(range(2018, 2026))          # prereg §6 outer test window
PRIOR_SEASONS = list(range(2014, 2018))          # seasons that build the 2018 fold's priors


import re  # noqa: E402

# Generational suffixes are dropped so one human keeps one id: sources write "Pete Carmichael" and
# "Pete Carmichael Jr." for the same man, and splitting them would fabricate two coaching careers
# out of one. Collisions between a genuine father/son pair in the same era would have to be handled
# by hand; none occur in this panel (checked: no two distinct NFL play-callers share a normalized
# name in 2014-2026).
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv)\b")


def person_id(name):
    """Stable identity key. Deliberately name-based: the same human keeps one id across every team
    and every job title he ever holds, which is the whole point of the identity layer."""
    if not isinstance(name, str) or not name.strip():
        return None
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower().replace(".", "").replace("'", "").replace("-", " ")
    s = _SUFFIX.sub(" ", s)
    return "_".join(s.split())


def load_context():
    hc_games = pd.read_csv(DATA / "head_coach_games.csv")
    ident = pd.read_csv(DATA / "coach_identity_team_season.csv")
    # authoritative head coach per (season, team): the one with the most games
    hc = (hc_games.groupby(["season", "team", "head_coach"])["game_id"].nunique()
          .reset_index(name="n").sort_values("n", ascending=False)
          .drop_duplicates(["season", "team"])[["season", "team", "head_coach", "n"]]
          .rename(columns={"n": "hc_games"}))
    games = hc_games.groupby(["season", "team"])["game_id"].nunique().reset_index(name="team_games")
    oc = ident[["season", "team", "nominal_oc", "oc_status"]]
    return hc, games, oc


def collect_rows():
    rows = []

    def add(season, team, pc, source_key, confidence, ambiguity="ok", week_start=1,
            week_end=None, note=None):
        s = SRC.SOURCES.get(source_key, {})
        rows.append(dict(season=season, team=team, actual_play_caller=pc,
                         person_id=person_id(pc), week_start=week_start, week_end=week_end,
                         source_key=source_key, source_url=s.get("url"),
                         source_date=s.get("date"), source_publisher=s.get("publisher"),
                         confidence=confidence, ambiguity_status=ambiguity, note=note))

    # NOTE: complement-derivation is FORBIDDEN by the ratified prereg -- a source that names only
    # the head-coach callers does not establish who called plays for the remaining teams, and the
    # nominal OC may never be substituted. 2018 is now covered by a direct 32-team source instead.

    # full-season attested tables
    for season, (table, key) in SRC.SEASON_TABLES.items():
        for team, pc in table.items():
            add(season, team, pc, key, "high")

    # team-by-team rows for the seasons with no compiled 32-team table
    for (season, team), (pc, key) in SRC.PC_PARTIAL.items():
        meta = SRC.PARTIAL_SOURCES[key]
        rows.append(dict(season=season, team=team, actual_play_caller=pc,
                         person_id=person_id(pc), week_start=1, week_end=None,
                         source_key=key, source_url=meta["url"], source_date=meta["date"],
                         source_publisher=meta["publisher"], confidence="high",
                         ambiguity_status="ok", note=meta["evidence"]))

    # explicitly unresolved
    for (season, team), meta in SRC.AMBIGUOUS.items():
        rows[:] = [r for r in rows if not (r["season"] == season and r["team"] == team)]
        add(season, team, None, meta["source_key"], "conflict", "unresolved", note=meta["reason"])

    # midseason changes: mark the team-season ambiguous unless a defensible week exists
    for (season, team), meta in SRC.MIDSEASON_CHANGES.items():
        existing = [r for r in rows if r["season"] == season and r["team"] == team]
        if meta.get("effective_week") and meta.get("to_pc") and meta.get("from_pc"):
            rows[:] = [r for r in rows if not (r["season"] == season and r["team"] == team)]
            w = meta["effective_week"]
            for pc, ws, we in ((meta["from_pc"], 1, w - 1), (meta["to_pc"], w, None)):
                rows.append(dict(season=season, team=team, actual_play_caller=pc,
                                 person_id=person_id(pc), week_start=ws, week_end=we,
                                 source_key="wikipedia", source_url=meta["source_url"],
                                 source_date=None, source_publisher="Wikipedia",
                                 confidence="high", ambiguity_status="split_midseason",
                                 note=meta["note"]))
        else:
            rows[:] = [r for r in rows if not (r["season"] == season and r["team"] == team)]
            rows.append(dict(season=season, team=team, actual_play_caller=None, person_id=None,
                             week_start=1, week_end=None, source_key="wikipedia",
                             source_url=meta["source_url"], source_date=None,
                             source_publisher="Wikipedia", confidence="conflict",
                             ambiguity_status="unresolved_midseason", note=meta["note"]))
        _ = existing
    return pd.DataFrame(rows)


def build():
    print("=" * 80)
    print("ACTUAL-PLAY-CALLER TABLE — assembly + coverage against the pre-registered gates")
    print("=" * 80)

    hc, games, oc = load_context()
    pc = collect_rows()

    # every (season, team) in the panel gets a row; missing ones are explicit UNKNOWNs
    grid = pd.MultiIndex.from_product(
        [PANEL_SEASONS, sorted(hc.team.unique())], names=["season", "team"]).to_frame(index=False)
    tbl = grid.merge(pc, on=["season", "team"], how="left")
    tbl = tbl.merge(hc, on=["season", "team"], how="left") \
             .merge(games, on=["season", "team"], how="left") \
             .merge(oc, on=["season", "team"], how="left")

    tbl["ambiguity_status"] = tbl["ambiguity_status"].fillna("unknown_no_source")
    tbl["confidence"] = tbl["confidence"].fillna("none")

    # ---- role DERIVED from the authoritative HC table; source labels never trusted
    tbl["hc_person_id"] = tbl["head_coach"].map(person_id)
    tbl["play_caller_role"] = np.where(
        tbl["person_id"].isna(), pd.NA,
        np.where(tbl["person_id"] == tbl["hc_person_id"], "head_coach", "offensive_assistant"))
    tbl["nominal_oc_person_id"] = tbl["nominal_oc"].map(person_id)
    tbl["pc_is_head_coach"] = np.where(
        tbl["person_id"].isna(), pd.NA, (tbl["person_id"] == tbl["hc_person_id"]))
    # is the play-caller ALSO the nominal OC? (metadata only, never used to assign)
    tbl["pc_is_nominal_oc"] = np.where(
        tbl["person_id"].isna(), pd.NA, (tbl["person_id"] == tbl["nominal_oc_person_id"]))

    # Games attributed to each play-caller stint — COUNTED, never week arithmetic (v3.2).
    #
    # The original implementation was `min(week_end, team_games) - week_start + 1`, which counts
    # WEEKS. A segment spanning a bye then over-counts: GB 2015 weeks 1-14 span 14 weeks but only
    # 13 GAMES. That was corrected once by a patch script, and a later rebuild of this file SILENTLY
    # REVERTED it — so the correct counting now lives here, making the builder idempotent.
    #
    # Historical seasons: every scheduled REG game was played, so distinct game_id in the week range
    # is the actual game count. Deploy season: the same count is the SCHEDULED-game count, which is
    # the documented prospective rule. `build_segment_offense.py` independently recounts from PBP and
    # asserts agreement, so a divergence between schedule and PBP cannot pass silently.
    tbl["week_end"] = tbl["week_end"].fillna(99)
    tbl["week_start"] = tbl["week_start"].fillna(1)
    gsrc = pd.read_csv(DATA / "head_coach_games.csv")[["season", "team", "week", "game_id"]].dropna()
    gsrc["week"] = pd.to_numeric(gsrc["week"], errors="coerce")
    counts = []
    for _, r in tbl.iterrows():
        if pd.isna(r["person_id"]):
            counts.append(0)
            continue
        m = ((gsrc.season == r["season"]) & (gsrc.team == r["team"])
             & (gsrc.week >= r["week_start"]) & (gsrc.week <= r["week_end"]))
        counts.append(int(gsrc.loc[m, "game_id"].nunique()))
    tbl["n_games_attributed"] = counts

    out_cols = ["season", "team", "person_id", "actual_play_caller", "play_caller_role",
                "week_start", "week_end", "n_games_attributed", "nominal_oc", "head_coach",
                "source_url", "source_date", "source_publisher", "confidence",
                "ambiguity_status", "pc_is_head_coach", "pc_is_nominal_oc", "note"]
    tbl = tbl[out_cols].sort_values(["season", "team", "week_start"]).reset_index(drop=True)
    tbl.to_csv(DATA / "actual_play_caller.csv", index=False)

    # ------------------------------------------------------------------ COVERAGE
    def cov(df, seasons, label, gate=None):
        """Row coverage counts each (season, team) ONCE regardless of how many caller segments it
        has, so a midseason split can never inflate the numerator. Game coverage is attributed
        games over actual team games, capped per team-season at the real schedule length."""
        d = df[df.season.isin(seasons)]
        ts = d.groupby(["season", "team"])["person_id"].apply(lambda s: bool(s.notna().any())) \
            .reset_index(name="resolved")
        att = d[d.person_id.notna()].groupby(["season", "team"])["n_games_attributed"].sum() \
            .reset_index(name="att")
        tot = games[games.season.isin(seasons)][["season", "team", "team_games"]]
        g = tot.merge(att, on=["season", "team"], how="left")
        g["att"] = np.minimum(g["att"].fillna(0), g["team_games"])
        row_cov = ts.resolved.mean() if len(ts) else 0.0
        game_cov = g["att"].sum() / g["team_games"].sum() if g["team_games"].sum() else 0.0
        out = dict(scope=label, team_seasons=len(ts), resolved=int(ts.resolved.sum()),
                   row_pct=round(100 * row_cov, 1), game_pct=round(100 * game_cov, 1))
        if gate is not None:
            out["gate"] = f"{gate}%"
            out["status"] = "PASS" if (row_cov >= gate / 100 and game_cov >= gate / 100) else "FAIL"
        return out

    print("\n--- COVERAGE vs PRE-REGISTERED GATES (T0) ---")
    reports = [cov(tbl, OUTER_SEASONS, "OUTER TEST 2018-2025", gate=95),
               cov(tbl, PRIOR_SEASONS, "PRIOR-BUILDING 2014-2017", gate=90),
               cov(tbl, [2026], "DEPLOY 2026"),
               cov(tbl, PANEL_SEASONS, "ALL 2014-2026")]
    print(pd.DataFrame(reports).fillna("").to_string(index=False))

    gate_fail = [r for r in reports if r.get("status") == "FAIL"]
    print(f"\nT0 COVERAGE GATE: {'FAIL' if gate_fail else 'PASS'}"
          + (f"  ({len(gate_fail)} scope(s) below threshold)" if gate_fail else ""))

    print("\n--- per-season coverage (team-seasons, splits counted once) ---")
    ps = (tbl.groupby(["season", "team"])["person_id"].apply(lambda s: bool(s.notna().any()))
          .reset_index(name="res").groupby("season")
          .agg(resolved=("res", "sum"), team_seasons=("res", "size")).reset_index())
    ps["pct"] = (100 * ps.resolved / ps.team_seasons).round(1)
    print(ps.to_string(index=False))

    print("\n--- confidence mix (resolved rows) ---")
    print(tbl[tbl.person_id.notna()].confidence.value_counts().to_string())

    print("\n--- role split (derived, not from source labels) ---")
    print(tbl[tbl.person_id.notna()].play_caller_role.value_counts().to_string())

    # source-label disagreements worth reporting
    print("\n--- SOURCE ROLE-LABEL CHECK (derived vs what a source called it) ---")
    hc_called = tbl[(tbl.play_caller_role == "head_coach")]
    print(f"  play-callers who ARE the head coach: {len(hc_called)}")
    oc_called = tbl[(tbl.play_caller_role == "offensive_assistant")]
    not_the_oc = oc_called[oc_called.pc_is_nominal_oc == False]  # noqa: E712
    print(f"  non-HC play-callers who are NOT the nominal OC: {len(not_the_oc)} "
          f"(these would have been MIS-ATTRIBUTED by a nominal-OC rule)")
    if len(not_the_oc):
        print(not_the_oc[["season", "team", "actual_play_caller", "nominal_oc"]]
              .head(20).to_string(index=False))

    print("\n--- UNRESOLVED / AMBIGUOUS CASES ---")
    unres = tbl[tbl.person_id.isna()]
    print(f"  total unresolved team-seasons: {len(unres)}")
    print(unres.ambiguity_status.value_counts().to_string())
    named = unres[unres.ambiguity_status != "unknown_no_source"]
    if len(named):
        print("\n  explicitly adjudicated as unresolved (not merely unsourced):")
        print(named[["season", "team", "ambiguity_status", "note"]].to_string(index=False))

    print(f"\nwrote {DATA/'actual_play_caller.csv'}  ({len(tbl)} rows)")

    write_source_ledger()
    return tbl


def write_source_ledger():
    """Emit source_ledger.csv WITH date provenance.

    This lives in the canonical builder, not in report_coverage.py, because the ledger and the
    play-caller table are mutually dependent artifacts read from the SAME source definitions. When
    the ledger was written by a separate reporting script, correcting a date in playcaller_sources
    updated actual_play_caller.csv while source_ledger.csv silently kept the stale value -- the
    repository held 2021-10-18 in one file and the fabricated 2021-01-01 in the other. Generating
    both from one call makes that divergence impossible.
    """
    import date_provenance as DP

    span = {}
    for season, (_table, key) in SRC.SEASON_TABLES.items():
        span.setdefault(key, []).append(season)

    # BOTH source dicts. PARTIAL_SOURCES carries the per-row 2014-2016/2019 research that makes up
    # the entire prior window -- omitting it from the ledger would leave the majority of sources
    # unaudited while the ledger looked complete.
    all_sources = {**SRC.SOURCES, **SRC.PARTIAL_SOURCES}

    rows = []
    for key, meta in all_sources.items():
        prov = DP.classify(key, meta.get("date"))
        lo, hi = DP.bounds(prov["source_date"], prov["source_date_precision"])
        rows.append(dict(
            source_key=key, source_kind=("season_table" if key in SRC.SOURCES else "per_row"),
            publisher=meta.get("publisher"),
            source_date=prov["source_date"],
            source_date_raw=prov["source_date_raw"],
            source_date_precision=prov["source_date_precision"],
            source_date_lower_bound=lo, source_date_upper_bound=hi,
            source_date_provenance=prov["source_date_provenance"],
            source_date_note=prov["source_date_note"],
            seasons=",".join(str(s) for s in sorted(span.get(key, []))) or "event",
            url=meta.get("url"), note=meta.get("note")))

    led = pd.DataFrame(rows).sort_values("source_key").reset_index(drop=True)
    led.to_csv(DATA / "source_ledger.csv", index=False)

    n_bad = int((led.source_date_precision.isin(["inferred", "missing"])).sum())
    print(f"wrote {DATA/'source_ledger.csv'}  ({len(led)} sources, "
          f"{n_bad} with inferred/missing dates -> never preseason-eligible)")
    return led


if __name__ == "__main__":
    build()
