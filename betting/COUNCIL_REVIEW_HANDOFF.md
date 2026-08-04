# Council review + fix session — HANDOFF (resume here)

Date: 2026-06-18. A 5-agent council reviewed this session's betting-execution code.
This file = what's fixed, what's left, and the one finding that changes the story.

## THE FINDING THAT MATTERS (corrects the prior conclusion)

The "HIGH tier beats the close 67% / 61% ATS-vs-close" result is **largely an
artifact, not validated edge.** Root cause: the model's #1 feature `spread_line`
is ~the CLOSING line (corr 0.994 to `spread_close`; it's the *only* line-derived
feature in `PROD_FEATURES_35` — verified). So `predicted_margin ≈ close + ~2pt
nudge`. The backtest picks at the OPEN and grades vs the CLOSE, so "beating the
close" is partly mechanical. Confirming check (Contrarian): predicted-margin MAE
beats the closing-line MAE by only **0.14 pt** — far too small for a real 61% ATS
edge. **The Kelly stakes were sized off this confounded number.** Must re-measure
honestly before trusting/sizing anything.

## FIXES ALREADY APPLIED THIS SESSION (tests green: odds 7, props 6, hist 3, kelly 4, shop 5)

In `betting/odds_client.py`:
- `clv_points`: corrected to **nflverse sign** (positive = home favored), matching
  the tracker + `clv_backtest`. Was inconsistent (sportsbook sign) — a live-path foot-gun.
- `consensus`: now stores spread in **nflverse sign** (negates the Odds-API home
  point) so `pick_line`/`closing_line` match `spread_line`; added `MIN_BOOKS=3` guard.
- `api_get`: catches `JSONDecodeError` (malformed 200 response).
- `snapshot_cmd`: `pick_line` is now **first-write-wins** (it's the CLV baseline;
  added `--force` to override); reports `unmatched`/`skipped` counts (no silent drop).
- `test_odds_client.py` updated for the new sign + min_books (7 tests).

## FIXES #1–#6 — ALL RESOLVED 2026-06-18 (kept for the reasoning; outcomes in the UPDATE at the bottom)

> **Read this before acting on anything below.** Every item in this section was completed the
> same day — the opening-line re-measurement was run (`experiments/walkforward_oos_preds_openline.csv`),
> and the Kelly stakes were re-fit off ATS-vs-open (HIGH 2%/bet, MEDIUM $0). The present-tense
> "do these next" framing is preserved as the record of the reasoning, **not as an open task list.**

### 1. (CRITICAL, methodology) Re-measure edge with the OPENING line, not the close
Add `--line {close,open}` to `experiments/walkforward_oos_preds.py`. For `open`:
after building `g`, **normalize franchise abbrevs** (OAK→LV, SD→LAC, STL→LA),
join `historical_lines.load_lines()` `spread_open` by (date, home, away), set
`g["spread_line"] = spread_open`, drop games with no open line, write
`walkforward_oos_preds_openline.csv`. (`spread_line` is the ONLY line feature, so
this fully de-confounds.) This mirrors production, where the model sees the
*current* line at pick time, not the future close. Then re-run `clv_backtest`
on that file → the HONEST edge; re-run `kelly_staking` → honest stakes. **Correct
the claim in `PRODUCTION_WIRING.md` + memory based on the result.**

### 2. (CRITICAL bug) Franchise join loss in `clv_backtest.run`
OOS preds use OAK/SD/STL; `historical_lines` uses LV/LAC/LA → inner join silently
drops 121/2227 (5.4%), biased toward relocated teams. FIX: normalize the preds'
`home_team`/`away_team` (OAK→LV, SD→LAC, STL→LA) before `.merge`; `print` a
warning if `len(df) < 0.95*len(preds)` listing unmatched (date,home,away). (Also
handles ~89 date off-by-one — consider a ±1-day join window.)

### 3. (HIGH bug) Pushes miscounted in `clv_backtest.won_ats`
`margin > spread_close` (strict) scores exact pushes (margin==close, common at
3/7) as away wins. FIX: drop `margin == spread_close` rows before the win rate.

### 4. (HIGH) Add ATS-vs-OPEN to `clv_backtest` + make tier method explicit
- The realized "what you'd actually win" = cover vs the OPEN you bet
  (`margin > spread_open`, excl pushes). Add it to `_summary` and LEAD with it
  (vs-close is the CLV-direction diagnostic only, not the bet win rate).
- Tracker has `ridge_predicted_margin`/`lgbm_predicted_margin` (no `xgb_margin`) →
  `voters.issubset` is False → silently falls back to `consensus_tier` (set vs the
  close). FIX: `print` which tier method was used; ideally alias the columns.

### 5. (HIGH bug) `props_scanner._events_on` hardcodes `commenceTimeFrom=2026-01-01`
→ any 2025 scan returns nothing (contradicts its own docstring example). FIX:
derive the floor from `args.date`.

### 6. (MED) `historical_lines.load_lines` season mislabel
`season = date.dt.year` puts Jan/Feb playoffs in the next year (phantom 2026).
FIX: `season = year - (month <= 2)`.

### 7. (MED/LOW, batch)
- `weekly_clv` weekday `auto`: Mon/Fri/Sat → "closing" foot-gun; only act
  Tue-Thu(pick)/Sun(closing), else no-op/warn. Document that "closing" = Sun-9am-ET
  snapshot, NOT the true close (in `weekly_clv.py` + `PRODUCTION_WIRING.md`).
- Record book **price** alongside pick/closing lines so CLV can be in cents, not
  just points (the whole stack silently assumes -110).
- `line_shopping.best_quote` picks max point ignoring juice — flag/EV-weight when
  the best-point book has materially worse price; guard `american(1.0)` div-by-zero;
  empty-slate header prints `[]`.
- `props_scanner`: pairs a **median** line with a **best** price (inflates EV),
  only flags the projection-favored side, unfitted SDs → print "directional, not
  bettable EV" in the scan output; consider widening SDs.
- `odds_client` totals consensus assumes Over/Under share a point (alt half-points
  drop the Under).
- `sys.path` import fragility — modules only run from `betting/`; anchor paths off
  `Path(__file__)` and confirm `python betting/weekly_clv.py` works from repo root.
- `fetch_lines` annotation should be `-> tuple[dict, dict]`.
- **Add an integration test for `clv_backtest.run`** (4-row preds+lines fixture
  asserting join count, push handling, tier method) — the buggy join seam is
  currently untested (would have caught #2/#3).
- Note `openpyxl` dependency for `historical_lines` (nfl.xlsx read).

## EXPANSIONIST opportunities (future, not bugs)
Extract a shared `odds_engine` (api_get/american/novig/kelly/wilson — duplicated
across NFL + sibling `soccer_model/`); anytime-TD model (Poisson on red-zone
usage — only year-round prop market); totals CLV (data already fetched, add
pick_total/closing_total to totals_tracker); middles/arb detection across the 9
books already pulled; multi-sport `ValueRow` seam; alt-lines.

## Agent transcripts (continue via SendMessage if needed)
Contrarian af237a17fc360bdb1 · First-Principles a8eca4035ac97dce0 · Expansionist
ae4ad3e22f26da5e9 · Outsider a0a4d50d693322664 · Executor a63b9bd20015c3235.

## UPDATE 2026-06-18 (later) — fixes #1-#6 DONE
- #1 DONE: `walkforward_oos_preds.py --line open` substitutes the opening line →
  `walkforward_oos_preds_openline.csv` (2138 games). **Honest result: model does
  NOT beat the close (HIGH beat-close 45%, avgCLV +0.28) — the +CLV claim was the
  artifact. **RETRACTED 2026-08-03:** the HIGH-tier ATS-vs-OPEN = 64% OOS (n~600) claim on
this line was ALSO an artifact — of a leaking sack feature plus an All-Pro identity
collision. Corrected in a pinned environment, HIGH is 129/238 = 54.2017%, Wilson lower
47.86%, BELOW the 52.4% break-even. No tier clears. See
`betting/experiments/audit_2026-08-03c_final/`. Historical text preserved below.** Kelly
  re-fit off ATS-vs-open: HIGH 2%/bet, MEDIUM $0. Docs + memory corrected.
- #2 DONE: clv_backtest franchise-normalizes (OAK→LV/SD→LAC/STL→LA) + warns on
  >5% join loss.
- #3 DONE: pushes excluded (NaN) in won_open/won_close.
- #4 DONE: ATS-vs-open is the headline; tier method printed explicitly.
- #5 DONE: props_scanner `_events_on` date floor derived from args.date.
- #6 DONE: historical_lines season = year - (month<=2).
- Plus: integration test for clv_backtest.run added (franchise join + pushes).

## STILL REMAINING (handoff #7 batch — lower priority)
weekly_clv weekday foot-gun + document "closing"=Sun-9am (not true close); record
book PRICE alongside lines (CLV in cents); line_shopping juice-aware best-quote +
american(1.0) guard; props median-line/best-price mismatch + "directional not
bettable" header; odds_client totals Over/Under-shared-point assumption; sys.path
import fragility; fetch_lines annotation; shared `odds_engine` extraction;
Expansionist opportunities (anytime-TD, totals CLV, middles/arb, multi-sport).

## STATE (as of 2026-06-18): clean; all modules import; nothing half-edited.

The test counts in this file are a 2026-06-18 snapshot and are **superseded**: `betting/` now
carries 77 test functions across 8 files (execution layer — odds 9, props 9, historical CLV 6,
kelly 4, line shopping 8, weekly CLV 10 — plus features 15 and calibration 16), and the full repo
suite is 213 passing. The execution-layer suites are now wired into CI (`test.yml`, `pytests` job,
`working-directory: betting`), which closes the "not in CI" gap recorded below.
