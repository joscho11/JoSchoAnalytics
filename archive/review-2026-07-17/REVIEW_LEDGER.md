# REVIEW LEDGER — full-repo review, 2026-07-17

Mode: HYBRID→FALLBACK. One subagent was launched for U4 (true isolation) and never
returned by reconciliation time; U4 was completed in main context (fallback). All
other units ran in fallback mode as pre-authorized. Independence caveat, stated
honestly: within a fallback unit, lens A and lens B were separate passes by the
same reviewer over one reading — procedural, not contextual, independence. If the
U4 subagent returns after this ledger, its findings become an addendum, not a
replacement. 14/14 passes complete.

## Master list (deduped; tag: source lenses)

| ID | Sev | Class | Type | File:line | Finding |
|---|---|---|---|---|---|
| L-1 (U1B-2=U7B-1, AGREED) | HIGH | GATED | TEST-GAP | .github/workflows/test.yml | fantasy/talent/tests/ (26, incl. golden regressions) + test_app_talent_columns.py (4, incl. H7 fence + all-tabs AppTest) run in NO CI job. Checkpoint-dependent tests would skip in CI; static/schema/fence tests would still protect. Proposed: explicit add to pytests + deploy-parity lists. |
| L-2 (U4A-1/U4B-3, AGREED-within-unit) | HIGH | GATED | RISK | betting/odds_client.py:208 | CLV snapshot rewrites the ENTIRE predictions_tracker.csv non-atomically (no tmp+replace, no row-count/schema assert). Intent is T5-compliant (fills reserved columns, first-write-wins pick_line); mechanism risks truncation/coercion of the forward record. Fix BEFORE the layer is wired for 2026 Week 1: tmp + os.replace + asserts. |
| L-3 (U3A-1, AGREED) | MED (fwd) / INFO (today) | GATED | RISK | betting/features.py:681 | KeyError 'coach' under pandas 3.x (local venv); CI pins 2.3.3 green → ENV DRIFT today, breaks at the future pin bump. Fix then, with pkl md5 byte-equivalence proof. |
| L-4 (U5B-1+U7B-3, AGREED) | MED | GATED-docs (partial SAFE-FIX) | DOCS-DRIFT | CLAUDE.md | Multipage st.Page refactor (app.py=70 lines, page_*.py, new CI page tests) vs CLAUDE.md's monolithic 167KB/8-tab description; stale cron-days + auto-commit claims. Dead URL corrected this session (safe-fix); section rewrite = owner. |
| L-5 (U1B-1, UNIQUE) | MED | GATED | RISK | fantasy/talent/config.py:57; archive_rho.py:27-34 | Machine-specific paths (C:/tmp WORK, user scratchpad) — non-portable builds; tests skip on fresh clone. Env-var override proposal. |
| L-6 (U6B-1, UNIQUE) | MED | GATED | TEST-GAP | fantasy/ weekly + dfs | Zero pytest coverage (inline notebook cells only). Low change-frequency; smoke test = new CI scope. |
| L-7 (U4B-1, UNIQUE) | MED | GATED | TEST-GAP | betting/test_*.py (5 files) | 26 execution tests not in CI; must land with the wiring change. |
| L-8 (U2B-1, UNIQUE) | LOW | INFO | RISK | draft_board_2026.py:102,230,259 | st.cache_data without ttl — stale overlay in a long process; mitigated daily by cron-commit → cloud redeploy. Document only. |
| L-9 (U1A-1, UNIQUE) | LOW | GATED | SMELL | composite.py:17,68 | Dual name-normalizers (norm_simple fallback vs _utils.norm_name) — unify only as a gated pipe-path change. |
| L-10 (U3A-2, UNIQUE) | LOW | GATED | SMELL | betting/features.py:466-471 | Silent empty-frame fallback on failed schedules load (coach features quietly degrade). |
| L-11 (U1B-3, UNIQUE) | LOW | INFO | RISK | build_rookie_score.py load_college | Network fetch on cache miss — documented non-hermetic path. |
| L-12 (U5B-2, UNIQUE) | LOW | INFO | RISK | 59 unsafe_allow_html sites | All self-built strings; only external HTML is TikTok oEmbed (accepted pattern). No action. |
| L-13 (U7B-4, UNIQUE) | LOW | GATED | SMELL | tests/golden/golden_ruled.json | Committed orphan (pre-split golden, read by no test). Removal = owner call. |
| L-14 (U2A-1, UNIQUE) | LOW | INFO | SMELL | draft_board_2026.py:213-214 | Fragile-but-correct ternary in &-chain (qb_rookie). Note for next board change. |

## FALSE-POSITIVE section (invariant screen catches — NOT findings)
- FP-1: board_adp_live daily churn — T10 (Class C by design).
- FP-2: research *_test.py scripts collectable by bare pytest — T6 (explicit CI lists are the designed defense; never run bare pytest at root).
- FP-3: sportsbook display negation in game cards — T3 (deliberate).
- FP-4: value-board blank calls — T4 (measured model blindness, by design).
- FP-5: retained build_draft_board.py not rendered — T7 (deliberate retention).
- FP-6: retrain_models.py writing pkls — designed manual retrain path.
- FP-7: QB unadjusted / no-floor / derived-k in talent — T9 (ruled design).
The screen caught 7 would-be findings. Nonzero = the screen worked.

## Counts (severity × class)
| | SAFE-FIX | GATED | INFO |
|---|---|---|---|
| HIGH | 0 | 2 (L-1, L-2) | 0 |
| MED | 1 partial (L-4 URL) | 4 (L-3, L-5, L-6, L-7) | 0 |
| LOW | 0 | 3 (L-9, L-10, L-13) | 4 (L-8, L-11, L-12, L-14) |

## SAFE-FIX log
- L-4 (partial): CLAUDE.md:11 dead URL "joschoanalytics.streamlit.app" →
  "joschoanalytics.streamlit.app" (dead-claim correction per cowork-docs-and-writing).
  Test: none applicable (docs). Proof: full-suite + hash sweep below.

## Verification (STOP 4 proof standard) — recorded after the gauntlet run
(see chat/final report: suite green, AppTest green, goldens unregenerated pass,
hash sweep diff empty except this ledger dir + CLAUDE.md.)

---

## ADDENDUM (post-ledger): the U4 subagent returned — reconciled

The U4 subagent completed AFTER the ledger was cut (712s runtime; its file writes
were harness-blocked, so the parent wrote findings_U4_lensA_subagent.md /
findings_U4_lensB_subagent.md on its behalf). Its pass was substantially deeper
than the parent's fallback pass. Reconciliation (parent verified both new HIGHs
against the code before accepting — quoted evidence confirmed at weekly_clv.py:65
and odds_client.py:177-208):

| ID | Sev | Class | Finding | Reconciliation tag |
|---|---|---|---|---|
| L-15 (sub U4A-1) | HIGH | GATED | weekly_clv.py:65 SimpleNamespace lacks `force`; odds_client.py:197 dereferences it -> deterministic AttributeError on the 2nd pick snapshot (the documented Thursday run); silent under the planned continue-on-error CI step | UNIQUE (subagent) — VERIFIED by parent |
| L-16 (sub U4A-2) | HIGH | GATED | snapshot match key = (home,away) only + optional --season/--week: the docstring's own bare closing snapshot can overwrite HISTORICAL tracker rows with today's lines | UNIQUE (subagent) — VERIFIED by parent |
| L-2 (upgraded) | HIGH | GATED | Non-atomic whole-log rewrite: parent U4A-1 = sub U4A-6 + U4B-7 | AGREED across two independent reviewers |
| L-17 (sub U4B-1/2) | HIGH | GATED | ZERO tests for weekly_clv.py and for snapshot_cmd — the exact modules the go-live wires; one two-run test would have caught L-15 | UNIQUE (subagent) |
| L-18 (sub U4A-3+U4B-6) | MED | GATED | line_shopping Over-favorability inverted for totals; existing fixture structurally cannot detect it | UNIQUE |
| L-19 (sub U4A-4) | MED | GATED | historical_lines totals pct: two denominators + silent NaN coercion | UNIQUE |
| L-20 (sub U4A-5) | MED | GATED | props EV: median line x max price, no min-books, no de-vig (half §7-known) | UNIQUE |
| L-21 (sub U4A-7) | MED | GATED | props date filter UTC-vs-ET drops SNF/MNF from scans | UNIQUE |
| L-22 (sub U4B-5) | MED | GATED | load_lines (Excel ingestion incl. the sign flip) untested | UNIQUE |
| L-23 (sub LOWs, batch) | LOW | GATED/INFO | U4A-8..13, U4B-8..16 (see subagent files) — incl. CLV rounding 1dp vs 2dp (a two-of-our-numbers-disagree item), tracker-lacks-xgb-column fallback, quota-burn loop | UNIQUE |
| — (sub U4B-17) | — | — | Security: clean (no hardcoded key; never logged) | AGREES with U7 scan |

Parent-fallback U4 items not found by the subagent: none unique (parent's U4A-1
absorbed into L-2; parent's math verifications AGREE with the subagent's).

## REVISED counts (supersede the table above)
| | SAFE-FIX | GATED | INFO |
|---|---|---|---|
| HIGH | 0 | 4 (L-1, L-2, L-15, L-16) + L-17 test-gap | 0 |
| MED | 1 partial (L-4 URL) | 9 (L-3, L-5, L-6, L-7, L-18..L-22) | 0 |
| LOW | 0 | L-9, L-10, L-13 + L-23 batch | L-8, L-11, L-12, L-14 |

NO fix from this addendum was applied — every item is execution-layer behavior
(GATED). The go-live implication is the headline: L-15 + L-16 + L-2 + L-17 should
land BEFORE PRODUCTION_WIRING step 2 executes for 2026 Week 1.


## RESOLUTIONS (appended 2026-07-27; findings above unmodified)

- **L-1 and L-7/L-17 — CLOSED.** Both "not in CI" gaps are gone. `.github/workflows/test.yml`
  now runs the betting execution layer (6 files, `working-directory: betting`) and
  `test_app_talent_columns.py` + both `fantasy/talent/tests/` files under the `pytests` job,
  and a third `deploy-parity` job re-runs the suites on Python 3.12 against `requirements.txt`
  as Streamlit Cloud resolves it. The test counts in the original rows are 2026-07-17 snapshots
  and are superseded — `betting/` now carries 77 tests across 8 files and the full repo suite is
  213 passing.
- **Still open from this ledger:** `test_nfl_qb_score.py` and `test_college_qb_score.py` (the
  talent-build suites added 2026-07-27) are in no CI job. They read the talent artifacts, which
  are untracked until committed, so wiring them into CI has to follow that commit.