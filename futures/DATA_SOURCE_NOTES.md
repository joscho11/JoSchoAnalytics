# Data source notes — NFL preseason team win totals

Written 2026-08-03, from the acquisition run recorded in
`futures/artifacts/win_totals_acquisition.json`. Producer: `futures/01_acquire_win_totals.ipynb`.

---

## 1. The source

**Covers *Sports Odds History*** — one archive page per NFL season:

```
https://www.covers.com/sportsoddshistory/nfl-win/?sa=nfl&t=win&y=<season>
```

Each page is static HTML with a single table, `<table class='soh1'>`, of seven columns:

| Team | Win Total | Over Odds | Under Odds | Week bet settled | Actual Wins | Result |
|---|---|---|---|---|---|---|

The first four are what this project uses. **`Actual Wins` and `Result` are parsed only to assert
the row layout and are never written to the output** — they are realized outcomes, and putting them
anywhere near the market file is exactly the leak `00_data_audit.ipynb` exists to prevent.

### Coverage, as probed

| | |
|---|---|
| Seasons with 32 team rows | **2010 – 2025** (16 seasons, 512 rows) |
| Default acquisition window | **2012 – 2025** (14 seasons, 448 rows) — widen with `-p START_SEASON 2010` |
| 2026 | Page exists, **zero team rows** — the upcoming season is not yet published |
| Rows per season | Exactly 32, every season |

---

## 2. Access and site policy

* **`robots.txt` permits this path.** At acquisition time the `User-agent: *` block carried **42
  `Disallow` rules and none matched `/sportsoddshistory/nfl-win/`**. The rules that exist protect
  forum write endpoints, account pages, geolocation/login APIs, and `SportsbookRedirect` / `/go/`
  affiliate links. The policy file is cached at `futures/data/raw/covers/robots.txt` and re-checked
  on every refresh — the notebook **refuses to fetch** if a matching rule ever appears.
* **Nothing is bypassed.** The pages are served as plain HTML to an ordinary GET. There is no
  paywall, no CAPTCHA, no bot-protection challenge, and no access control involved.
* **Request rate:** one GET per season, ≥1 second apart (default 3.0s), and only when
  `REFRESH_RAW=True`. After the first population every run reads the local cache. The full archive
  is 14–16 requests, once.
* **Attribution:** every output row carries `market_source = "Covers Sports Odds History"` and the
  exact `source_url` it came from.

### Manual fallback

If automated retrieval ever becomes unavailable (policy change, bot protection, layout change), the
pipeline still works — the notebook only needs the raw HTML on disk:

1. Open `https://www.covers.com/sportsoddshistory/nfl-win/?sa=nfl&t=win&y=<season>` in a browser.
2. Save the page as HTML to `futures/data/raw/covers/<season>.html` (one file per season).
3. Add an entry per season to `futures/data/raw/covers/fetch_manifest.json`:
   ```json
   "2019": {"url": "https://www.covers.com/sportsoddshistory/nfl-win/?sa=nfl&t=win&y=2019",
            "http_status": 200, "retrieved_at": "2026-08-03T00:00:00+00:00",
            "bytes": 553214, "sha256": "<sha256 of the saved file>"}
   ```
   The manifest is not decoration: `retrieved_at` is written into every output row, and the notebook
   verifies each file against its recorded `sha256`.
4. Run `papermill futures/01_acquire_win_totals.ipynb /tmp/out.ipynb -p FORBID_NETWORK True`.
   Everything downstream is identical.

---

## 3. What the source does **not** provide

### 3.1 No sportsbook identity — the blocker that keeps gate C shut

The pages publish a number and both prices but **never name the book that posted them**. Covers is
an *archive*, not a sportsbook.

`book` is therefore written **null on all 352 rows**. It is not filled with `"Covers"`, and the
notebook asserts it stays null so a later edit cannot quietly satisfy the gate with a fabricated
sportsbook. PREREGISTRATION §2.2 as originally frozen requires a named book, so **every row fails
G3-C** — the gate that §10 Amendment 1 left untouched and that is the sole key to §7 gate C. Under
the amendment's **G3-B** (archive path: point-in-time + a named `market_source`, `book` may be null)
all 352 rows count, which is what carries G1 and G2.

This matters beyond bookkeeping: §7's gate **C** (the only gate that unlocks side, probability, or
profitability language) is defined against *the posted price at a specific book*. Without book
identity, a price is a market observation of unknown origin — usable for describing where the market
sat, not for claiming what could have been transacted.

### 3.2 Date-only timing, usually on kickoff day

Each page carries at most one `As of <date>` line, with **no clock**. Compared against Week 1 from
the repository's own `futures/data/schedules_snapshot.parquet`:

| Status | Seasons | Count |
|---|---|---|
| **`strictly_before_week1`** (satisfies §2.2 as frozen) | 2014, 2015, 2016, 2017, 2018 — each exactly 3 days before | **5** |
| **`same_day_as_week1_kickoff`** | 2019, 2020, 2021, 2022, 2024, 2025 (also 2010, 2011) | **6** in window |
| **`no_date_at_source`** → rejected | 2012, 2013, 2023 | **3** |

The 2023 page carries no date but states, in prose: *"Closing odds prior to each teams' first game"*.
That is a claim about timing, not a date, and the notebook does not convert prose into a timestamp.

Read together, the same-day pattern and that note say the archive stores the **closing preseason
number**, captured at or immediately before Week 1. Economically that is the *better* snapshot — the
most informed preseason price. For §2.2 it is worse: a date equal to the kickoff date cannot
*demonstrate* strict priority, even though an evening kickoff makes it overwhelmingly likely in fact.

Those rows are written with their true dates and a **`point_in_time_status`** column. The frozen
audit excludes them; Amendment 1 admits them for Tier B, separately counted and never pooled
silently. They are neither hidden nor laundered under either rule.

**Second, independent blocker — resolved for Tier B only.** Under the frozen rule, 5 seasons
demonstrate pre-Week-1 timing against a G1 threshold of 8. Amendment 1's kickoff-day clause (A1.3)
admits the six same-day seasons on the source's own closing statement, reaching 11 — and requires
the strictly-dated five to be carried as a mandatory sensitivity on every reported number. Under
the frozen path (`-p TIER_B_ARCHIVE False`) the answer is still NO-GO.

---

## 4. Output

`futures/data/win_totals.csv` — **352 rows × 13 columns**, sha256
`dd6753f654dec864b7fbeb7e3e23b7a3fa2cfc41c86e1de48c66bb86742eecbe`, sorted by `(season, team)`.

| column | notes |
|---|---|
| `season` | integer NFL season |
| `team` | canonical franchise abbreviation |
| `win_total_line` | float, half-point increments; observed range **3.5 – 12.5** |
| `price_over`, `price_under` | American odds, nullable Int64; observed **−270 … +230** |
| `book` | **always null** — see §3.1 |
| `market_source` | `Covers Sports Odds History` |
| `as_of_date` | ISO date from the page's `As of` line |
| `source` | `covers_sportsoddshistory_nfl_win` |
| `source_url` | the exact season page |
| `retrieved_at` | UTC ISO, **from the fetch manifest**, not the clock — this is what makes reruns byte-identical |
| `raw_team_name` | the displayed name, unmodified |
| `point_in_time_status` | `strictly_before_week1` or `same_day_as_week1_kickoff` — **extra column beyond §2.2's eight; the audit reads the eight it needs and ignores the rest** |

**34.1% of lines are integers**, so pushes are real and must be excluded from both numerator and
denominator of any hit-rate metric (PREREGISTRATION §4) and modelled explicitly in `03`.

### Settlement assumptions — carried, not resolved

The source states no settlement rule. This project assumes PREREGISTRATION §2.1: **a tie counts as
half a win**, the near-universal convention. Since `book` is unknown, the rule that *would have
applied* to these specific numbers is also unknown. `wins` (strict) is carried alongside
`wins_half_ties` in the outcome table so any row can be re-graded if a book with different rules is
ever identified.

---

## 5. Team-name mapping

37 displayed names → 32 canonical franchises, mapped **explicitly** (no fuzzy matching, no prefix
heuristics). Relocations and renames map to the **current** abbreviation, matching how
`00_data_audit.ipynb` normalizes its outcome table, so a franchise joins across a move:

| displayed | → |
|---|---|
| `Oakland Raiders`, `Las Vegas Raiders` | `LV` |
| `San Diego Chargers`, `Los Angeles Chargers` | `LAC` |
| `St Louis Rams`, `Los Angeles Rams` | `LA` |
| `Washington Redskins`, `Washington Football Team`, `Washington Commanders` | `WAS` |

`raw_team_name` preserves the as-played display value on every row. An unmapped name is a hard
failure, never a guess.

---

## 6. Rejections

96 rows rejected, all for one reason: **`no_date_at_source`** — the whole of 2012, 2013 and 2023
(32 rows each). Every rejection is listed individually in
`futures/artifacts/win_totals_acquisition.json` with its season, team, reason, and the raw values.

One further row exists outside the default window: **2011 Indianapolis Colts**, whose win total and
both prices are blank at source (the Peyton Manning neck-injury preseason, when the number was
pulled). It rejects as `missing_or_unparseable_win_total` if you widen with `-p START_SEASON 2010`.
It is not imputed.

---

## 7. Leakage controls

* Realized outcomes (`Actual Wins`, `Result`) are **discarded at parse time**; an assertion checks no
  outcome-named column survives into the frame.
* **No line is reconstructed** from game spreads, ratings, or any model.
* **No value is inferred from realized wins.**
* **No current-season information fills a historical value** — each season's numbers come only from
  that season's own page.
* Week 1 dates come from the repository's pinned schedule snapshot, so the point-in-time test is
  evaluated against this project's own data.

---

## 8. Reproducibility

* Raw HTML is pinned in `futures/data/raw/covers/` (**8.2 MB**, 14 files + manifest + robots.txt),
  each with a recorded sha256 that is re-verified on every run.
* `retrieved_at` comes from the manifest, so the output does not depend on the clock.
* **Proven, not asserted:** the notebook was executed twice — once with `REFRESH_RAW=True` (live
  fetch) and once with `FORBID_NETWORK=True` (sockets replaced by a raising stub). Both produced
  `dd6753f6…`, byte-for-byte identical, 84,222 bytes.
* Reproducibility means *from these pinned inputs*. Covers could revise a historical page at any
  time — which is precisely why the raw bytes and their hashes are kept.

**Housekeeping note for Joseph:** `futures/data/` is **not** in `.gitignore` (only `betting/data/`
is), so the 8.2 MB raw cache and the schedule snapshot are currently untracked-but-trackable. Track
them for full reproducibility, or add an ignore rule and treat the cache as local — your call, not
mine to make.

---

## 9. Status

**`GO-TIER-B`** under `PREREGISTRATION.md` §10 **Amendment 1** (accepted by Joseph 2026-08-03,
frozen before notebooks `02`-`05` were opened). Audit run of 2026-08-03:

| Gate | Result | Observed |
|---|---|---|
| G1 >= 8 usable seasons | **PASS** | 11 (2014-2022, 2024, 2025) |
| G2 >= 28/32 teams per counted season | **PASS** | 32 |
| **G3-B** point-in-time + named `market_source` (archive path, Tier B only) | **PASS** | 352 valid of 352 |
| **G3-C** strictly pre-kickoff + **named book** (frozen rule; the only key to §7 gate C) | **FAIL** | **0 valid of 352** |
| G4 outcome-table integrity | PASS | 24 complete seasons |

**What this licenses.** §7 gates **A and B only**: projection quality, and whether the projection was
closer to the realized win count than the **archived market consensus**, in aggregate - reported
twice, headline (10 folds / 320 rows) and the mandatory A1.4 strict-subset sensitivity (2015-2018,
4 folds / 128 rows, formally **underpowered** and therefore never the headline).

**What stays locked.** §7 gate **C** is unreachable from this source: no sides, no probability
against a posted line, no confidence tiers, no EV, no profitability, and none of the words *bet*,
*edge*, *lock*, *value*, *play*. `tier_c_open` is recorded as `false` in
`futures/artifacts/data_audit.json` on every run, and the audit is written so that no setting of
`TIER_B_ARCHIVE` can produce a plain `GO` - that requires G3-C, which requires a named book.

**How it must be named.** An *archived market consensus of unattributed sportsbook origin*. Never
"the sportsbook line", never "Vegas", never "the market". **Exact closing timestamps are
unavailable** (A1.3) and that limitation travels with every result.

**For anything priced**, collect 2026 lines prospectively - timestamped and book-attributed. That is
the only route to G3-C, and no amendment substitutes for it.

Run `-p TIER_B_ARCHIVE False` to reproduce the pre-amendment gate exactly; it returns **NO-GO** with
0 valid rows, which is the frozen behaviour verified on 2026-08-03.
