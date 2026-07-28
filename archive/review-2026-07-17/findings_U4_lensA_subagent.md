# U4 Lens A — SUBAGENT pass (returned post-ledger; written by parent on its behalf)
# Parent independently verified U4A-1 and U4A-2 against the code before accepting.

| ID | Sev | Type | file:line | Finding |
|---|---|---|---|---|
| U4A-1 | HIGH | BUG | weekly_clv.py:65 -> odds_client.py:197 | SimpleNamespace(which,season,week) lacks `force`; snapshot_cmd evaluates `not args.force` when a row already has pick_line -> deterministic AttributeError on the SECOND pick snapshot (the documented Thursday run). Crash is pre-write (no corruption) but post-API-spend; under the planned continue-on-error CI step it fails silently every week. VERIFIED BY PARENT. |
| U4A-2 | HIGH | BUG/RISK | odds_client.py:177-181,191,197-208 | Row match key is (home_team,away_team) ONLY and --season/--week are optional; the docstring's own bare `snapshot --which closing` iterates the WHOLE tracker and always refreshes closing_line/clv -> historical rows whose matchup repeats on the currently posted board get overwritten with today's lines. weekly_clv always scopes (safe); the manual CLI is the foot-gun. VERIFIED BY PARENT. |
| U4A-3 | MED | BUG | line_shopping.py:59,63,66-73 | best_quote favors max point for ALL sides — inverted for totals OVER (lowest total is best); shop_gain reports the harm as gain. Mitigated: unwired + UNDER-only fence. Existing test can't catch it (identical 47.5 fixture). |
| U4A-4 | MED | BUG | historical_lines.py:76-78 | Totals movement: mean over dropna but pct over ALL rows (NaN>=1.0 -> False) — two denominators, pct understated. Go/no-go verdict keys off spread, unaffected. |
| U4A-5 | MED | RISK | props_scanner.py:107-111,127-134 | Prop EV pairs MEDIAN line with MAX price (different books/lines), no min-books guard (n=1 accepted), no de-vig — best-of-N selection bias. Line/price half is §7-known; min-books half is new. |
| U4A-6 | MED | RISK | odds_client.py:176,208 | Whole-forward-log read_csv->to_csv round trip for <=3-cell updates (dtype/format churn on the append-only artifact). = parent U4A-1; AGREED dual-reviewer. |
| U4A-7 | MED | BUG | props_scanner.py:150-152 | Date filter compares UTC commence date to the user's ET date -> SNF/MNF night games silently excluded from scans ("no value" reads as no-edge, is no-data). |
| U4A-8 | LOW | BUG/SMELL | odds_client.py:117-123 | min_books guards spreads only; totals median can rest on 1-2 books while n_books reports the spread universe. |
| U4A-9 | LOW | BUG | odds_client.py:154 vs clv_backtest.py:39 | CLV rounding 1dp live vs 2dp backtest; quarter-point CLV banker-rounds to ±0.2. |
| U4A-10 | LOW | BUG | kelly_staking.py:106-109 | Recommendation prints only total_note[0] and claims other tiers fail even if MEDIUM also cleared (latent while MEDIUM=$0). |
| U4A-11 | LOW | RISK | clv_backtest.py:61-65 | Merge without duplicate-key guard; dup fan-out double-counts and can suppress the >5% join-loss warning (dropped can go negative). |
| U4A-12 | LOW | RISK/DOCS | clv_backtest.py:80-90 | Tracker has ridge_/lgbm_predicted_margin, NO xgb column -> default run always falls back to close-derived consensus_tier (printed honestly; council #4 alias never done). |
| U4A-13 | LOW | RISK | props_scanner.py:81-84 | Projections keyed by normalized name; collisions silently last-write-win. |

Math verified correct (not findings): kelly_fraction, wilson_lower, breakeven=1/dec,
american_to_decimal, push exclusion both sides, clv_points sign both impls, ingest
negation (odds_client.py:121), historical sign flip + season derivation, franchise
normalization + join-loss warning. Write-path inventory: snapshot_cmd is the ONLY
writer; no pkl/frozen writes; tests are hermetic (temp files/monkeypatch).
Coverage: 12/12 + wiring docs + tracker/openline headers. HIGH present: U4A-1, U4A-2.
