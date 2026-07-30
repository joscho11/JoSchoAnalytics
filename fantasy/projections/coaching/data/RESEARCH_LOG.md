# Actual-play-caller research log

Table checksum (md5): `98f1c66b7387c16bba6a5463f4e0fa06`

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

## v3.9 (2026-07-29) — the SOURCE DATE now gates historical features too, not just identity

Retrospective attribution above is unchanged. What changed is how that attribution may be USED.

Through v3.8, the point-in-time gate applied only to a target season's EXPECTED CALLER. The
historical caller record fed Arms 1/2/4 ungated, so an article published after season *s* could build
a feature for a target season between *s* and the article. Concrete case from this table:

> **BUF 2014** is attributed by an ESPN piece dated **2016-10-29**
> (`.../jacksonville-jaguars-fire-offensive-coordinator-greg-olson-promote-qb-coach-nathaniel-hackett`).
> Under the old rule that segment entered target-2015 caller history. It could not have been known in
> 2015. It is now admitted only from target **2017** onward.

Design A therefore requires, for a historical segment to feed target season Y:
`segment season < Y` **AND** the attributing source's conservative UPPER bound `<= Y`'s frozen
projection cutoff. Missing and inferred dates are never eligible, as before.

**Measured effect on the research asset — eligible / prior resolved segments by target season:**

| target | eligible | prior | | target | eligible | prior |
|---|---|---|---|---|---|---|
| 2015 | **15** | 27 | | 2021 | 206 | 222 |
| 2016 | 38 | 63 | | 2022 | 237 | 252 |
| 2017 | 77 | 95 | | 2023 | 267 | 282 |
| 2018 | 119 | 130 | | 2024 | 299 | 314 |
| 2019 | **154** | 163 | | 2025 | 331 | 346 |
| 2020 | 170 | 189 | | 2026 | 364 | 378 |

The gate bites hardest exactly where the archive is thinnest, which is the correct direction.

**Consequence for research priority.** Point-in-time IDENTITY coverage on the outer window is
152/256, but the number that actually bounds the caller channel is how many team-seasons have an
identified caller *with any eligible prior history*: **25 / 3 / 4 / 7 / 6 / 26 / 26 / 27** of 32 for
2018–2025. 2019–2022 are nearly empty. The highest-value remaining research is therefore a qualifying
**pre-cutoff** league-wide source for 2019, 2020, 2021 and 2022 — not more retrospective attribution,
which is already at 95.3%. Design B (oracle, ungated) exists to measure what such a source would be
worth: it sees 244/256 identities and materially more history.

Returning-caller continuity remains REFUSED on principle. No new source was recovered in this pass;
no row of the table changed; the checksum above is unchanged.

## v3.9a (2026-07-29) — the gate is now AUDITABLE per segment, and it is a DECISION PENDING

Two additions, no change to the table or its checksum.

**1. Per-segment audit trail.** `arm_feature_lineage_v39.csv` now carries **1,631**
`caller_contribution` rows: one per candidate historical segment behind each target-season caller
aggregate, **included or excluded**, with the segment key, source season/team/week range, `pbp_games`,
the attributing source's upper bound, the target cutoff, gate eligibility and — when excluded — the
reason from a closed set (`attributing source postdates the target cutoff`,
`attributing source has no usable date`). Design A: **618** segment-contributions included, **35**
excluded by the gate. Design B: **978** included (it gates nothing). Reconciled against the feature
tables on all 416 rows of both designs.

So the research question "which citation is doing the work for this feature, and which citation was
thrown away?" is now answerable per row, which it was not before.

**2. The gate itself is awaiting Joseph's ratification.**
> **SUPERSEDED by the v3.9b entry below — RESOLVED, and the cost figure in this paragraph was WRONG.**
> The claim that it "is the difference between Design A seeing 124/256 known-with-history rows and a
> ceiling of 200/256" is **RETRACTED**: Design A has only 152/256 known identities, so that ceiling was
> never reachable, and the realised difference is **zero rows**. Retained as history only.

The rule that a historical segment must be established by a source published before the TARGET season's
cutoff was my addition, not part of the brief. Full framing in `../V39_PREFIT_STOP_REPORT.md` §7.

**Research priority is unchanged either way**, and this is the useful part for the log: the binding
constraint is a qualifying **pre-cutoff** league-wide caller source for **2019, 2020, 2021, 2022**. Under
the strict rule those seasons have 3/4/7/6 usable rows out of 32. Retrospective attribution is already
95.3% and more of it does not help Design A at all under the strict rule — only pre-cutoff evidence does.

## v3.9b (2026-07-29) — the source-date gate on HISTORY is RETIRED, and it never mattered

**Decision adopted.** The target-season expected caller stays evidence-gated at the preseason cutoff.
Once he is known, his history uses the FULL retrospective ledger restricted to seasons strictly before
Y — a past segment is no longer gated by the publication date of the surviving citation. The past
play-calling role was a contemporaneously observable fact; the citation date records when I can prove it,
not when it became knowable.

**The measured effect, which retracts two earlier claims from this project's own reporting:**

| Design A, outer 2018-2025 | strict gate | primary (retired gate) |
|---|---|---|
| known target identity | 152 | 152 |
| known WITH history | 124 | **124 — ZERO change** |
| known NO history | 28 | 28 |
| caller-games of history | 7,274 | **7,632 (+358)** |

Retracted: "Design A known-with-history can rise toward Design B's 200/256, ~76 more usable rows."
Impossible — an unknown target identity stays at the league prior however complete the ledger is, so the
ceiling is 152 and the arithmetic maximum is 28. Retracted too, implicitly: even 28 is not attained.

**Why zero.** All 28 known-no-history rows are genuine FIRST-TIME play-callers — Daboll 2018, Kellen
Moore 2019, Joe Brady 2020, Monken/Slowik/Canales 2023, Grubb/Coen/Callahan 2024, Caley/Engstrand/
Patullo/Grizzard 2025, and so on. They have **no prior segment in the ledger at all**. The gate was never
what suppressed them; a missing archive citation was never their problem.

**Per-season game gain:** 2018 +106 · **2019 +0** · 2020 +16 · 2021 +42 · 2022 +16 · 2023 +71 ·
2024 +71 · 2025 +36. Exactly one row anywhere gains history: **2016 DET, Jim Bob Cooter, 0 → 9 games.**

**Consequence for research priority — unchanged, and now sharper.** Retiring the gate does **not**
relieve 2019-2022. Those seasons are thin because their TARGET identities are unknown (25 of 32 unknown
in 2019), not because their history was gated. The single binding constraint remains a qualifying
**pre-cutoff league-wide play-caller source for 2019, 2020, 2021 and 2022**. Nothing about historical
attribution completeness substitutes for it, and this pass proves that quantitatively rather than
asserting it.

The retired rule stays measurable: `strict_gate_sensitivity()` in memory, plus
`strict_source_date_gate_would_exclude` / `strict_gate_exclusion_reason` on every contribution row of
`arm_feature_lineage_v39.csv`. Table and checksum unchanged; no new source recovered in this pass.

## v3.9c (2026-07-29) — the lineage artifact now STATES the adopted policy

No change to the table, its checksum, or any research finding. One documentation defect mattered enough
to record here, because this log is where a future reader checks what rule produced a feature:

Through v3.9b the generated `arm_feature_lineage_v39.csv` still carried, on **every** caller-history and
caller-continuity row, the two **RETIRED** strings quoted here for traceability only —
RETIRED: `timing_rule = "…Design A additionally requires source upper bound <= Y cutoff"`, and
RETIRED note: `"…openers are themselves gated on Y's cutoff"`.
The feature VALUES already used the adopted ungated policy, so the artifact documented a rule it was not
applying. An MD5 cannot see that kind of contradiction.

Corrected to the pinned wording — *"source seasons < Y from the FULL retrospective caller-attribution
ledger; NOT gated by the attributing source's publication date"* — with a semantic validator
(`validate_lineage_policy`) wired into the runtime preflight so a reintroduction fails a check rather
than merely changing a hash. The retired rule stays measurable per row via
`strict_source_date_gate_would_exclude` / `strict_gate_exclusion_reason`.

**Research priority unchanged:** a qualifying **pre-cutoff** league-wide play-caller source for
**2019, 2020, 2021, 2022**.

## Standard applied

Only sources that explicitly name who CALLED OFFENSIVE PLAYS qualify. Excluded by rule: search-result snippets, AI summaries, forum posts, fan sites, inference from the nominal-OC title, and complement-inference from a list naming only head-coach callers. The 2018 complement derivation used in the previous revision was removed and replaced with a direct 32-team source.