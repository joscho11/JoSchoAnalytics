# Actual-play-caller research log

Table checksum (md5): `ac9883e98cdb1bd04a1c0978746cc023`

## Coverage vs pre-registered gates (T0)

| scope | gate_pct | team_seasons | resolved | row_coverage_pct | game_coverage_pct | attributed_games | total_games | status |
|---|---|---|---|---|---|---|---|---|
| OUTER TEST 2018-2025 | 95 | 256 | 244 | 95.3 | 95.4 | 4058 | 4254 | PASS |
| PRIOR-BUILDING 2014-2017 | 90 | 128 | 116 | 90.6 | 90.6 | 1856 | 2048 | PASS |

## Seasons with no qualifying source

`2014, 2015, 2016, 2019` — 20 team-seasons.

## Search avenues attempted

- **ESPN annual '32 playcallers' series** — FOUND 2017, 2023, 2024, 2025. Series does not extend back beyond 2017; no 2014/2015/2016/2019 edition exists.
- **Yardbarker 'ranking the offensive play-caller' series** — FOUND 2020, 2021, 2022, 2024. No 2014-2016 or 2019 edition indexed.
- **Fantasy Index 'play callers 1 thru 32' (Ian Allan)** — FOUND 2018, 2023, 2026. A 2020-09-01 mailbag reference exists but the ranking is subscriber-only; 2019 not located.
- **PFF play-caller rankings** — FOUND 2018 (7 teams only), 2019 (3 teams only), 2022 (6 teams only). All are top-N features, not 32-team tables -- insufficient for coverage.
- **Wikipedia team-season articles, full-text play-calling mine** — 448 cached articles scanned; 40 candidate sentences over 27 team-seasons (6.0%). Mostly game-recap criticism of a play call. Yielded midseason-change events, not baseline attribution.
- **Wikipedia coach biographies** — Play-calling stated only incidentally. McDaniel and Stefanski articles contain zero play-calling sentences.
- **Pro Football Reference coach pages** — HTTP 403 to all automated access, with and without a browser user-agent. PFR carries no play-caller field regardless.
- **Wayback Machine CDX, espn.com 32for32 + *playcaller* patterns** — 32for32 hits are a generic paginated series, not year-specific playcaller articles. Zero *playcaller* URLs archived.
- **The Ringer NFL play-calling network feature** — Narrative coaching-tree piece. Confirmed to contain no per-team-season play-caller table.
- **nflverse data catalog** — Head coach only (load_schedules home_coach/away_coach). No coordinator or play-caller field anywhere in the catalog.
- **PFF exports on disk (409 CSVs)** — No coach, coordinator, or play-caller column in any file. Confirmed by header scan across all NFL and college tables.

## Standard applied

Only sources that explicitly name who CALLED OFFENSIVE PLAYS qualify. Excluded by rule: search-result snippets, AI summaries, forum posts, fan sites, inference from the nominal-OC title, and complement-inference from a list naming only head-coach callers. The 2018 complement derivation used in the previous revision was removed and replaced with a direct 32-team source.