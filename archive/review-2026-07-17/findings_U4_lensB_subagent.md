# U4 Lens B — SUBAGENT pass (returned post-ledger; written by parent on its behalf)

| ID | Sev | Type | file:line | Finding |
|---|---|---|---|---|
| U4B-1 | HIGH | TEST-GAP | weekly_clv.py (all 70 lines) | The one module PRODUCTION_WIRING wires into CI has ZERO tests (no test_weekly_clv.py): weekday auto-select, current_target window/NaT, offseason no-op, missing tracker, snapshot arg contract — one two-run test would have caught U4A-1. |
| U4B-2 | HIGH | TEST-GAP | odds_client.py:173-217 | snapshot_cmd — the only writer of the forward log — entirely untested (first-write-wins, --force, clv compute, scoping, round-trip integrity). |
| U4B-3 | MED | RISK | test.yml absence | Known 26-tests-not-in-CI gap ASSESSED: low while unwired; go-live wires weekly_clv under continue-on-error with no CI tests -> deterministic Thursday crash (U4A-1) ships silently exactly at Week 1. |
| U4B-4 | MED | RISK | weekly_clv.py:26 + siblings | Bare sibling imports (§7-known): CLI + betting/-cwd pytest fine; import-as-library (planned app.py surfacing, papermill) breaks. OOS_PREDS cwd-relative is the exception to safe pathing (U4B-15). |
| U4B-5 | MED | TEST-GAP | historical_lines.py:37-58 | load_lines untested: Home-Line sign negation (a regression silently flips the whole backtest), season derivation, aliases, silent dropna loss. |
| U4B-6 | MED | TEST-GAP | test_line_shopping.py:11-13,47 | Identical-47.5 totals fixture structurally cannot detect the U4A-3 Over inversion; no divergent-point totals test. |
| U4B-7 | MED | RISK | odds_client.py:208 | Non-atomic in-place to_csv onto the forward log; crash truncates; races the Actions bot commit when wired. = parent U4A-1 (AGREED). |
| U4B-8 | LOW | BUG | props_scanner.py:120,204 | --markets outside DEFAULT_SD -> raw KeyError after quota spend. |
| U4B-9 | LOW | RISK | historical_lines.py:24,39 | Missing nfl.xlsx/openpyxl -> raw traceback, transitively kills clv_backtest/kelly_staking. |
| U4B-10 | LOW | BUG | line_shopping.py:24 | american(1.0) ZeroDivisionError (§7-known, open). |
| U4B-11 | LOW | RISK | line_shopping.py:59 | best-quote tie-break rides API book order — cross-call nondeterminism of reported book. |
| U4B-12 | LOW | SMELL | line_shopping.py:95-105 | Empty-slate prints []; "(N books)" is top-row home-side count, mislabeled (§7-known). |
| U4B-13 | LOW | SMELL | odds_client.py:71,86-90 | sys.exit inside library functions — kills any embedding process (planned app.py step 4). |
| U4B-14 | LOW | RISK | weekly_clv.py:52 | §7 weekday foot-gun assessed: crons align; manual off-day runs degrade to no-ops, not bad writes. Sun-9am != true close = documented invariant, screened. |
| U4B-15 | LOW | DOCS | kelly_staking.py:11,23; odds_client.py:126 | OOS_PREDS cwd-relative breaks the docstring's repo-root invocation; fetch_lines annotation says dict, returns tuple (§7-known). |
| U4B-16 | LOW | RISK | weekly_clv.py:48; props_scanner.py:180-182 | Raw ValueError on bad --date; per-event odds loop with no cap flag vs ~500/mo quota. |
| U4B-17 | — | SECURITY clean | odds_client.py:56-72 | No hardcoded secret; key never logged on error paths. |

Coverage: 12/12 + wiring docs + headers + __init__/conftest absence verified.
HIGH present: U4B-1, U4B-2.
