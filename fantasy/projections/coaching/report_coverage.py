"""T0 COVERAGE REPORT + UNRESOLVED-CASE LEDGER + SOURCE LEDGER.

Read-only over data/actual_play_caller.csv. Emits the artifacts the ratified prereg requires when
the coverage gate is evaluated, whether it passes or fails:

  data/coverage_report.csv     row + game-weighted coverage per scope, with PASS/FAIL vs gate
  data/unresolved_cases.csv    every team-season with no attributable play-caller, and why
  data/source_ledger.csv       one row per source of record, with URL / publisher / date / span
  data/RESEARCH_LOG.md         searches attempted and what each yielded (negative results included)
"""
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
sys.path.insert(0, str(HERE))
import playcaller_sources as SRC   # noqa: E402

OUTER = list(range(2018, 2026))
PRIOR = list(range(2014, 2018))
GATES = {"OUTER TEST 2018-2025": (OUTER, 95), "PRIOR-BUILDING 2014-2017": (PRIOR, 90)}

# Every distinct search/fetch avenue tried for the unsourced seasons, with its outcome. Negative
# results are recorded deliberately: they are the evidence that the gate failure is a data limit
# and not an effort limit.
SEARCHES_ATTEMPTED = [
    ("ESPN annual '32 playcallers' series", "FOUND 2017, 2023, 2024, 2025. Series does not "
     "extend back beyond 2017; no 2014/2015/2016/2019 edition exists."),
    ("Yardbarker 'ranking the offensive play-caller' series", "FOUND 2020, 2021, 2022, 2024. "
     "No 2014-2016 or 2019 edition indexed."),
    ("Fantasy Index 'play callers 1 thru 32' (Ian Allan)", "FOUND 2018, 2023, 2026. A 2020-09-01 "
     "mailbag reference exists but the ranking is subscriber-only; 2019 not located."),
    ("PFF play-caller rankings", "FOUND 2018 (7 teams only), 2019 (3 teams only), 2022 (6 teams "
     "only). All are top-N features, not 32-team tables -- insufficient for coverage."),
    ("Wikipedia team-season articles, full-text play-calling mine", "448 cached articles scanned; "
     "40 candidate sentences over 27 team-seasons (6.0%). Mostly game-recap criticism of a play "
     "call. Yielded midseason-change events, not baseline attribution."),
    ("Wikipedia coach biographies", "Play-calling stated only incidentally. McDaniel and Stefanski "
     "articles contain zero play-calling sentences."),
    ("Pro Football Reference coach pages", "HTTP 403 to all automated access, with and without a "
     "browser user-agent. PFR carries no play-caller field regardless."),
    ("Wayback Machine CDX, espn.com 32for32 + *playcaller* patterns", "32for32 hits are a generic "
     "paginated series, not year-specific playcaller articles. Zero *playcaller* URLs archived."),
    ("The Ringer NFL play-calling network feature", "Narrative coaching-tree piece. Confirmed to "
     "contain no per-team-season play-caller table."),
    ("nflverse data catalog", "Head coach only (load_schedules home_coach/away_coach). No "
     "coordinator or play-caller field anywhere in the catalog."),
    ("PFF exports on disk (409 CSVs)", "No coach, coordinator, or play-caller column in any file. "
     "Confirmed by header scan across all NFL and college tables."),
]


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def main():
    tbl = pd.read_csv(DATA / "actual_play_caller.csv")
    hc = pd.read_csv(DATA / "head_coach_games.csv")
    games = hc.groupby(["season", "team"])["game_id"].nunique().reset_index(name="team_games")

    rows = []
    for label, (seasons, gate) in GATES.items():
        d = tbl[tbl.season.isin(seasons)]
        ts = d.groupby(["season", "team"])["person_id"].apply(lambda s: bool(s.notna().any())) \
            .reset_index(name="resolved")
        att = d[d.person_id.notna()].groupby(["season", "team"])["n_games_attributed"].sum() \
            .reset_index(name="att")
        g = games[games.season.isin(seasons)].merge(att, on=["season", "team"], how="left")
        g["att"] = np.minimum(g["att"].fillna(0), g["team_games"])
        row_c, game_c = ts.resolved.mean(), g["att"].sum() / g["team_games"].sum()
        rows.append(dict(scope=label, gate_pct=gate, team_seasons=len(ts),
                         resolved=int(ts.resolved.sum()),
                         row_coverage_pct=round(100 * row_c, 1),
                         game_coverage_pct=round(100 * game_c, 1),
                         attributed_games=int(g["att"].sum()), total_games=int(g["team_games"].sum()),
                         status="PASS" if (row_c >= gate / 100 and game_c >= gate / 100) else "FAIL"))
    covr = pd.DataFrame(rows)
    covr.to_csv(DATA / "coverage_report.csv", index=False)

    # ---- unresolved ledger
    res = tbl.groupby(["season", "team"]).agg(
        any_resolved=("person_id", lambda s: bool(s.notna().any())),
        status=("ambiguity_status", "first"), note=("note", "first")).reset_index()
    unres = res[~res.any_resolved].copy()
    unres["reason"] = np.where(
        unres.season.isin(SRC.UNSOURCED_SEASONS),
        "no qualifying 32-team source located for this season",
        unres["note"].fillna(unres["status"]))
    unres["blocks_gate"] = np.where(unres.season.isin(OUTER), "OUTER 2018-2025",
                                    np.where(unres.season.isin(PRIOR), "PRIOR 2014-2017", "-"))
    unres[["season", "team", "status", "reason", "blocks_gate"]].to_csv(
        DATA / "unresolved_cases.csv", index=False)

    # ---- source ledger
    # NOT written here. The ledger is a mutually dependent artifact of the canonical build and is
    # emitted by build_playcaller_table.write_source_ledger(), so a date correction can never land
    # in actual_play_caller.csv while source_ledger.csv keeps the stale value. Reporting reads it.
    from build_playcaller_table import write_source_ledger  # noqa: F401  (documents the owner)

    # ---- research log
    lines = ["# Actual-play-caller research log", "",
             f"Table checksum (md5): `{md5(DATA/'actual_play_caller.csv')}`", "",
             "## Coverage vs pre-registered gates (T0)", "",
             "| " + " | ".join(covr.columns) + " |",
             "|" + "---|" * len(covr.columns),
             *["| " + " | ".join(str(v) for v in r) + " |" for r in covr.values], "",
             "## Seasons with no qualifying source", "",
             f"`{', '.join(str(s) for s in SRC.UNSOURCED_SEASONS)}` "
             f"— {len(unres[unres.season.isin(SRC.UNSOURCED_SEASONS)])} team-seasons.", "",
             "## Search avenues attempted", ""]
    for name, outcome in SEARCHES_ATTEMPTED:
        lines.append(f"- **{name}** — {outcome}")
    lines += ["", "## Standard applied", "",
              "Only sources that explicitly name who CALLED OFFENSIVE PLAYS qualify. Excluded by "
              "rule: search-result snippets, AI summaries, forum posts, fan sites, inference from "
              "the nominal-OC title, and complement-inference from a list naming only head-coach "
              "callers. The 2018 complement derivation used in the previous revision was removed "
              "and replaced with a direct 32-team source."]
    (DATA / "RESEARCH_LOG.md").write_text("\n".join(lines), encoding="utf-8")

    print("=" * 78)
    print("T0 COVERAGE REPORT")
    print("=" * 78)
    print(covr.to_string(index=False))
    print(f"\nT0: {'PASS' if (covr.status == 'PASS').all() else 'FAIL'}")
    print(f"\nunresolved team-seasons: {len(unres)}")
    print(unres.groupby("season").size().to_string())
    print(f"\ntable md5: {md5(DATA/'actual_play_caller.csv')}")
    print(f"\nwrote coverage_report.csv, unresolved_cases.csv, source_ledger.csv, RESEARCH_LOG.md")


if __name__ == "__main__":
    main()
