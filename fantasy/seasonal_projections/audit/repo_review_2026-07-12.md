# Independent repo + product review — 2026-07-12

Read-only audit session (interrupted once by a PC restart; resumed via the
session-resume protocol — state reconciled from disk, nothing re-run that had
already landed). Scope: shipped 2026 Draft Board + dashboard, deploy parity,
docs/public-surface accuracy, content-law fence, structure. **No fixes were
applied; this file is the session's only write.** Frozen artifacts were read
but never modified. Joseph commits.

Baseline at review start: working tree clean except
`?? fantasy/seasonal_projections/content/` (board content-sourcing sheet,
untracked, reviewed — no findings; its header carries the licensed-framing
note). Nothing staged. 245 tracked files.

---

## Test + render evidence (what this review stands on)

- **CI suite list (test.yml `pytests` job), local run:** 33 passed / 0 failed,
  12.5s, zero warnings in pytest output. Interpreter: AI_hedge_fund venv
  (see environments table) — local green is advisory; CI pins are the arbiter.
- **AppTest full render of app.py:** 0 exceptions, 0 rendered `st.error`;
  3 `st.warning` boxes, all intentional honesty banners (agent-picks
  underperformance note, totals "Tracking only — do not bet.", league-history
  "Most Unlucky"). 18 tab containers, 15 dataframes.
- **Deprecation warnings captured verbatim during the render** (streamlit
  1.58.0 logs, repeated per call site):
  > Please replace `use_container_width` with `width`.
  > `use_container_width` will be removed after 2025-12-31.
  > For `use_container_width=True`, use `width='stretch'`. For
  > `use_container_width=False`, use `width='content'`.

  > Please replace `st.components.v1.html` with `st.iframe`.
  > `st.components.v1.html` will be removed after 2026-06-01.
- **Board loader exercised standalone** (`draft_board_2026._load_board_2026()`):
  180 rows / 180 unique player_ids; populations stable_role 102 /
  volatile_rb_wr 60 / volatile_qb_te 18; talent join complete (0 unmatched);
  worked example (Jordyn Tyson) renders with all fields; download CSV emits
  (13,915 bytes).

---

## HIGH

**H1. Two streamlit APIs the app depends on are past their announced removal
dates, while the deploy floats.** `use_container_width` (removal date
2025-12-31 — 7 months past): 18 call sites in `app.py` (first at app.py:399,
sidebar logo; the rest across Track Record / Weekly Fantasy / League History
tables and charts) + 1 in `film_room.py:113`. `st.components.v1.html`
(removal date 2026-06-01 — 6 weeks past): `film_room.py:49`, the TikTok
embed — its removal breaks the entire Film Room tab. `requirements.txt:18`
pins `streamlit>=1.30,<2.0`, so the next upstream release that executes
these removals breaks the live site on a routine cloud rebuild with zero
repo changes. The board tab itself is safe (already on `width="stretch"`).

**H2. The deployed environment is the only untested one.** Four environments
exist (table below): CI tests exact pins on Python 3.11; local tests run on
packages that sit *outside* the deploy constraints (pandas 3.0.3 vs `<3.0`,
numpy 2.4.6 vs `<2.0`); Streamlit Cloud runs Python 3.12 (`runtime.txt`) with
floating-latest resolutions of `requirements.txt`. No suite anywhere
exercises py3.12 + floating streamlit/pandas/numpy — the combination serving
users. Compounding: `requirements.txt:27-28` exact-pins `llama-index==0.11.0`
+ `llama-index-llms-anthropic==0.2.0` (mid-2024 vintage, unused by the app —
see S3) whose stale transitive constraints are the likeliest resolver
conflict on a 3.12 rebuild.

**H3. Live player-level verdict copy on the fantasy surface.**
`video_content.py:32` ("The Market Is Wrong About Brian Thomas Jr.") +
subtitle `video_content.py:33` ("Sleeper ADP WR31, our model WR17") +
`video_breakdowns/brian_thomas_jr.md:1` (same H1 title) render live in the
Film Room tab. This is a named-player market-is-wrong verdict on the same
projections-vs-price axis the shipped board is licensed on, where the fence
(draft_board_2026.py:4-9, from H6/H11/H12 licensing) permits aggregate
patterns only, never player-level claims. The video predates the fence
(posted 2026-07-07) and is already public on TikTok — **needs Joseph's
ruling**: leave as grandfathered historical content, soften the in-app
title/subtitle, or add a dated "made before the aggregate-only labeling
standard" note. Flagged as HIGH for visibility, not because the fix is
obvious.

## MEDIUM

**M1. Kenny Gainwell renders with a blank Draft Price, Gap, and Proj position
rank, and his row parks at the bottom of the board.** Chain: Sleeper carries
"Kenny Gainwell" (ADP 109.8, overall #114); `season_dataset_2014_2026.csv`
carries him as "Kenneth Gainwell" (nflverse name), so the
`["season","norm_name","position"]` merge at build_season_dataset.py:465-466
misses → dataset ADP NaN → the board's player_id ADP merge
(draft_board_2026.py:79,84) returns NaN → `sort_values("adp_half_ppr")`
(draft_board_2026.py:246) puts him last with a blank price. **Bounded check:
this is the ONLY such miss** — 1 of 245 Sleeper-2026 ADP rows fails the join,
confirmed name-variant (last-name+position match). Fix direction (not
applied): a Kenny→Kenneth alias in `_utils.norm_name` or the dataset build,
then dataset regen. The artifact side of his row is F1 below
[FROZEN — Joseph's call].

**M2. Root README and CLAUDE.md describe the retired Draft Value Finder as
the live product.** README.md:169 (tab list names "a pre-season Draft Value
Finder"; actual tab is "📋 Draft Board"), README.md:171 (full DVF
description, "🔥 Consensus values" box, "who the draft room is mispricing"),
README.md:269-272 (`build_value_board.py` as "Builds the live tab data";
`surprise_eval.py` "can we spot over/undervalued players"). CLAUDE.md:13
("surfaced as the Draft Value Finder dashboard tab — our model's calls vs
ADP"), CLAUDE.md:88 ("7 tabs ... 📋 Draft Value Finder (tab5)" — there are 8
tabs and tab5 is the 2026 Draft Board), CLAUDE.md:460-492 ("ADP-MISPRICING
SKILL" framing with hit-rates — pre-fence wording). Also CLAUDE.md:559's two
"known follow-ups needing Joseph's ruling" are both already resolved in the
tree (`test_app_draft_board.py` was retargeted to the 2026 board and passes;
the Help & Guide DVF copy is gone — only comment refs remain at
app.py:1701,1705) — the note itself is now stale.

**M3. `fantasy/seasonal_projections/README.md` is entirely pre-ship.** Lines
12-14 present "**BUY** (undervalued) / **FADE** (overvalued) calls with
confidence tiers → `value_board_{season}.csv` → the app tab" as the product;
line 55 same; line 74 claims "our BUYs aren't more injury-prone than the
field (~14% vs ~18%)"; lines 81-84 label `build_value_board.py` "SHIPPED tab
data". The shipped pipeline (phase4_band.py → apply_board_labels.py →
build_talent_index.py → draft_board_2026.py) and the licensed-label regime
appear nowhere. This README is the closest doc to the research directory a
public visitor reads.

**M4. requirements.txt floor understates what the code needs.**
`streamlit>=1.30` (requirements.txt:18) permits versions without the
`width="stretch"` API used at draft_board_2026.py:255,339,380 (needs ≥~1.49)
and without `st.dialog` used behind a guard at film_room.py:63. The floor has
never bound in practice (cloud floats to latest) but is wrong as a statement
of compatibility.

## LOW

**L1. Board download CSV ships internal column names and display strings.**
draft_board_2026.py:318-322 exports `view[cols]` verbatim: headers
`player_disp, position_disp, adp_half_ppr, p50_disp, ...` and cells like
"104 (35th %ile)" / "Travis Kelce ⚠". Fine for eyeballs, unfriendly for a
spreadsheet user; header rename + numeric p50 column would fix it.

**L2. app.py:1701 banner comment** still reads "TAB 5: SEASONAL VALUE FINDER
— our model's calls vs the draft room (ADP)" — comment-only, but it is both
stale (tab is the 2026 Draft Board) and pre-fence framing ("our model's
calls"); the license-clean framing is "the market's estimate + our band".

**L3. `fantasy/fantasy_agent.ipynb:156`** — weekly-fantasy agent prompt uses
"= undervalued" in its instruction text. Weekly start/sit context, not the
seasonal board; lowest-priority fence hit.

**L4. Advanced-view label table repeats identical strings 180×**
(draft_board_2026.py:375-380): `signal_status`, `plain_label`, `disclosure`
have only 3 distinct values across the board; a per-population legend (3
rows) would read better and shrink the DOM. Cosmetic.

**L5. Streamlit honesty-warning render cost**: the three `st.warning` banners
are correct product behavior; noting only so a future reviewer doesn't
mistake AppTest's `warnings: 3` for a defect.

## REPORT-ONLY [FROZEN — Joseph's call]

**F1. `phase4_band_2026.csv` row 53 (Kenny Gainwell, 00-0036919):**
`value_gap` and `p_bust` fields are empty in the frozen artifact (trailing
`,` — verified at byte level). Every other row has a `value_gap`. Empty
`p_bust` is shared by design with all late picks (see F2); the empty
`value_gap` is unique to him and is the artifact-side twin of M1. Any repair
means regenerating a frozen, hash-referenced artifact — Joseph's call.

**F2. `p_bust` coverage is positional by design:** populated only for QB/TE
adp_pos_rank ≤ 12 and RB/WR ≤ 24 (108 of 180 rows empty). Matches phase0's
bust convention; the board only surfaces it in the advanced view where blanks
render empty. Worth one sentence in the seasonal README when it gets its
rewrite (M3) so the blanks read as design, not data loss.

**F3. Retired-engine verdict artifacts are tracked in a public repo:**
`value_board_2025.csv` / `value_board_2026.csv` carry per-player BUY/FADE
calls + tiers; `draft_board_2025.csv` / `draft_board_2026.csv` (seasonal
root) are the older VOR-era boards; `models/*.pkl` (Model A / rookie PPG)
feed only the retired engine. The shipped board's fence forbids exactly this
language on live surfaces; these files are not rendered anywhere but are
published by being tracked (and remain in git history regardless). Options
when convenient: untrack from HEAD, or leave with a README status note.

**F4. Research scripts containing fence language** (BUY/FADE/tiers/
mispricing): `build_value_board.py`, `adp_value_model.py`, `fade_deep_dive.py`,
`value_eval.py`, `surprise_eval.py`, `opportunity_features.py`,
`train_model_a.py`, `college_rookie_test.py`, `incoming_competition.py`.
Legitimate closed-campaign research code; listed for completeness only. The
BUY/FADE grep hits inside `snapshots/*.parquet` are binary false positives.
`PREREGISTRATION.md` mentions the terms by necessity (it defines the fence).

**F5. Ledger consistency check — PASSES.** All five results JSONs present and
match the campaign ledger: H6 pooled +0.300 vs bar 0.083 PASS; H7 −0.013 FAIL
("true r up to ~0.115 not excluded"); H8v −0.009 FAIL; H11 r_FINAL +0.296 vs
bar 0.081 PASS (freshness share +0.075 descriptive); H12 +0.254 vs bar 0.089
PASS. `phase4_validation.json` = v2, coverage 79.4%/49.8%, known P(top-12)
high-decile wobble documented. PREREGISTRATION.md tail is the phase4
engineering-validation note; nothing appended since the board ship. Both 2026
CSVs are valid UTF-8 with zero mojibake sequences (earlier console "â€""
sightings were PowerShell display decoding, not file corruption).

---

## Environments (citable)

| Package | Local venv (AI_hedge_fund, py 3.11.9) | requirements.txt (cloud constraints) | CI pins (requirements-ci/test.txt, py 3.11) | Streamlit Cloud actual (runtime.txt py-3.12) |
|---|---|---|---|---|
| streamlit | 1.58.0 | >=1.30,<2.0 | 1.57.0 (test) | floats → latest 1.x |
| pandas | **3.0.3 (outside <3.0)** | >=2.0,<3.0 | 2.3.3 | floats → latest 2.x |
| numpy | **2.4.6 (outside <2.0)** | >=1.24,<2.0 | 1.26.4 | floats → latest 1.x |
| plotly | 6.8.0 | >=5.17,<7.0 | 6.7.0 (test) | floats |
| scipy | 1.17.1 | >=1.10,<2.0 | 1.16.3 (test) | floats (unused by app) |
| xgboost | 3.2.0 | >=2.0,<4.0 | 3.1.2 (ci) | floats (unused by app) |
| catboost | 1.2.10 | >=1.2,<2.0 | 1.2.10 (test) | floats (unused by app) |
| pytest | 9.1.1 | — | 9.0.2 (test) | — |

Local-only state a remote reviewer can't see: `BettingEdgeContinued/.venv`
has no interpreter (site-packages only — unusable; the AI_hedge_fund venv is
the working interpreter); `.env` present and properly gitignored
(.gitignore:2); `.streamlit/secrets.toml` present locally and untracked
(correct — GA credentials); `.pytest_cache/` and `__pycache__/` present and
untracked; the only untracked repo content is
`fantasy/seasonal_projections/content/` (sourcing sheet).

## Structure assessment (4d — judgment only, nothing moved)

**(i) Layout fitness.** `fantasy/seasonal_projections/` root holds ~70 files
in four unmarked generations: shipped product (phase4_band.py,
apply_board_labels.py, build_talent_index.py, build_rank_equiv_reference.py
+ their four CSV artifacts + season_dataset_2014_2026.csv), frozen campaign
evidence (h6/h7/h8v/h11/h12 harnesses + results JSONs, PREREGISTRATION.md),
the retired value-board engine (build_value_board.py, board_view.py,
models/*.pkl, value_board_*.csv, build_draft_board.py lineage), and
superseded/orphaned data (season_dataset_2014_2025.csv,
season_dataset_2002_2025.csv — the A4-FAIL extension artifact, 4.6MB).
For the post-campaign phase (product + content work) the flat layout makes
every session re-derive which files are load-bearing. Cheapest adequate fix:
a **status manifest table in the seasonal README** (file → shipped / frozen /
retired / superseded), which M3's rewrite needs anyway. A directory split
(product/ vs research/) would be cleaner but touches paths hardcoded in
draft_board_2026.py, tests, and the skills — only worth it with a full
AppTest + suite pass, and not this session.

**(ii) Misplaced / orphaned / public-presence-wrong.** The F3 verdict
artifacts (public-presence question). `season_dataset_2002_2025.csv`
(orphaned by the A4 gate — config stays 2014+). `betting/archive/
BettingEdgeContinued.ipynb` (10.6MB archived notebook blob). ~100MB of
tracked data overall (features_dataset.csv 31MB, raw_dataset.csv 24.5MB,
snapshots/ ~35MB) — defensible for reproducibility, but the repo is heavier
than its product needs; `data_audits/` tracks only 7 small manifest files
(the 17.5GB stays local — correct). `content/` (untracked) and this
`audit/` dir are new conventions — worth a one-line note in the seasonal
README when tracked.

**(iii) Requirements structure.** The dashboard imports exactly: streamlit,
pandas, plotly, requests, nflreadpy (lazy, app.py:185; brings polars +
pyarrow) + stdlib + local modules (calibration.py = math + pandas;
draft_board_2026.py = pandas). Today's `requirements.txt` additionally ships
xgboost, scikit-learn, lightgbm, catboost, scipy, joblib, pulp, papermill,
ipykernel, llama-index (×2, exact-pinned 2024 versions), python-dotenv,
matplotlib, seaborn — none imported on any app path (DFS tab reads
precomputed CSVs; no joblib/pkl loads in app.py). **A deploy/dev split is
warranted**: a lean `requirements.txt` (the six real deps, floors raised to
honest minimums per M4) for Streamlit Cloud, and a `requirements-dev.txt`
inheriting it for notebooks/research. Cuts cloud build time, removes the H2
llama-index resolver risk, and makes the deploy surface auditable at a
glance. CI pins stay the arbiter as today.

## Quality-of-life candidates (NOT implemented — pick freely)

1. M1 fix (Gainwell alias + dataset regen) restores his real price (109.8)
   and Gap to the board — highest user-visible value per line changed.
2. L1: rename download-CSV headers to the on-screen labels + numeric
   Expected column.
3. Pre-empt H1 mechanically: swap the 19 `use_container_width` sites to
   `width=` and film_room's `components.html` to `st.iframe` — app-wide
   change, needs the full AppTest sweep per the standing rule (and CI's
   streamlit pin bumped to a version supporting both, ≥1.58).
4. "How to read this board" expander (draft_board_2026.py:209,
   `expanded=True`) takes half a screen every visit; default-collapsed after
   launch week is a one-character change.
5. L4: replace the 180-row verbatim-label table with a 3-row per-population
   legend.
6. Film Room: `_oembed_html` failures currently fall back silently to a
   blockquote that renders blank when TikTok's embed.js is blocked; a
   caption-level "open on TikTok" note would cover the offline case
   (film_room.py:42-49).

---

*Method note: severity reflects impact on the live public product first,
docs/repo hygiene second. Everything above was verified against the tree at
review time; file:line refs are to the working tree of 2026-07-12. The
betting product's spreads/ATS language was out of scope for the fantasy
fence per the review brief.*

---

## Correction log (appended — original text above unchanged)

**2026-07-12 (fix session, R4):** M1's dataset-side defect corrected at the
builder level: `SLEEPER_NAME_ALIASES` added to `_utils.py` ("kenny
gainwell" → "kenneth gainwell") and applied to the ADP frame at both merge
sites (`build_2026_board.py`, `build_season_dataset.py`);
`season_dataset_2014_2026.csv` regenerated via `build_2026_board.py`.
Line-level diff vs the pre-fix file: exactly one line changed — Gainwell's
2026 row (ADP 109.8, overall rank 114, pos rank 37, sleeper_pts 116.2 now
populated; all other 8,273 lines byte-identical). `phase4_band_2026.csv`
remains FROZEN and untouched: his Gap and Proj position rank stay blank in
the artifact, and the board now renders a missing Gap as "–"
(`draft_board_2026.py` gap_disp). His Draft Price and board sort position
are restored.

---

## Resolution log â€” cleanup arc close-out (2026-07-12)

Append-only. One line per finding. Fixed / deferred / ruled, with a file reference where one
applies. Earlier text above is unchanged.

### Audit findings

- **H1 (deprecated `use_container_width` + `components.html`)** â†’ FIXED: 19 `use_container_width`
  sites migrated to the `width=` API across `app.py` + `film_room.py`; `components.html` â†’
  `st.iframe` in `film_room.py`; `streamlit==1.59.1` pinned in `requirements.txt` +
  `requirements-test.txt`.
- **H2 (deploy-combination untested; local pandas-3 failures)** â†’ RESOLVED: pin/docs; cloud
  parity 64/64; `betting/features.py:675` flagged for any future pandas-3 migration. (The two
  local `test_features.py` failures are the local venv's pandas 3.0.3 only; the cloud resolution
  passes all 64.)
- **H3 (Film Room "The Market Is Wrong About Brian Thomas Jr." single-player verdict)** â†’ RULED:
  archive-in-place â€” card retained with the archive frame (`video_content.py` `archived` flag +
  the always-visible note in `film_room.py`); no other site-voice verdict text survives on the card.
- **M1 / F1 (Gainwell blank Draft Price / Gap; band CSV)** â†’ FIXED: `SLEEPER_NAME_ALIASES` builder
  alias (`_utils.py`); `season_dataset_2014_2026.csv` regenerated with a one-line diff (Gainwell's
  2026 row only; see the R4 note above); `phase4_band_2026.csv` left FROZEN, blank Gap renders "â€“".
- **M2 / L2 (stale docs: retired Value Finder, tab list, repo map, CLAUDE.md bulk)** â†’ FIXED:
  `README.md`, `fantasy/seasonal_projections/README.md` (strike-don't-replace), and `CLAUDE.md`
  (Completed Work moved to `memory/completed-work-log.md`; refreshed to the closed campaign +
  shipped board; 40% of original by content) all refreshed; `app.py` tab5 header comment updated.
- **M3 (band `p_bust` coverage / design note)** â†’ FIXED via the docs refresh: the band's
  populated-only-for-early-picks behavior is documented in the board copy / `ARTIFACTS.md`; no code
  change (the CSV is FROZEN).
- **M4 (streamlit floor `>=1.30` predates `width=` API)** â†’ FIXED: superseded by the exact
  `streamlit==1.59.1` pin.
- **L1 (board CSV download shipped internal column names)** â†’ FIXED: export renames to the
  on-screen headers at download time only (`draft_board_2026.py`); the rendered table is unchanged.
- **F3 (value_board / draft_board CSVs tracked)** â†’ RULED: `value_board_2025.csv` +
  `value_board_2026.csv` git-rm'd (tip only; history preserves them); `draft_board_2025.csv` +
  `draft_board_2026.csv` and `models/*.pkl` retained (bounded 3f check: no verdict columns).

### Deferred (no fix this session; reason recorded)

- **L3 (`fantasy_agent.ipynb` "undervalued")** â†’ DEFERRED: notebook copy, not a shipped board
  surface; out of the fantasy-board fence scope for this arc.
- **L4 (180Ã— repeated licensed-label table in the advanced view)** â†’ DEFERRED: cosmetic; the
  `phase4_band_2026.csv` schema is FROZEN, and de-duping is a display refactor for a later pass.
- **Structure-(ii) orphans (`season_dataset_2002_2025.csv`, the 10.6 MB archive notebook)** â†’
  DEFERRED: Joseph instructed no touch of the extended dataset in any way; both catalogued in
  `ARTIFACTS.md` (RETIRED) rather than moved.
- **QoL â€” advanced-view expander default** â†’ DEFERRED: UX preference, not a defect.
- **QoL â€” Film Room offline fallback** â†’ DEFERRED: `st.iframe` degrades to TikTok's own
  unavailable state offline; a custom fallback is optional polish.
- **League History default-fetch-on-load** â†’ PARTIALLY ADDRESSED in 5g (default emptied + fetch
  gated behind a non-empty numeric ID; neutral first-person resting prompt; `APP_OFFLINE` honored).
  Residual: the placeholder still shows an example ID (a hint, not a default â€” no fetch fires from
  it). No further residual.

### New work landed this arc (not from the audit)

- **3d** â†’ `st.secrets` read guarded: a missing `secrets.toml` degrades to analytics-off, never a
  crash (`app.py`).
- **3e** â†’ GA upgraded: canonical `joschoanalytics.streamlit.app` page_location, `utm_*` query
  params appended to the pageview, once-per-session `board_view` event on the Draft Board tab.
- **3g** â†’ `.claude/settings.local.json` untracked (`git rm --cached`; stays on disk, already
  gitignored).
- **3h (voice sweep)** â†’ public-facing copy converted we/our/us â†’ I/my/me across
  `draft_board_2026.py`, `app.py` (Help + tab copy), `film_room.py`, `video_content.py`; licensed
  verbatim strings untouched.
- **4a** â†’ requirements split: `requirements.txt` trimmed to the true dashboard import closure;
  research/notebook-only packages moved to `requirements-research.txt`.
- **4b** â†’ deploy-parity CI job added to `.github/workflows/test.yml` (Python 3.12,
  `requirements.txt` as the cloud resolves it, all six suites).
- **4c** â†’ hermetic board test: `APP_OFFLINE=1` disables every network path so
  `test_app_draft_board.py` runs with zero network.
- **5f** â†’ new version-controlled skill `.claude/skills/subproject-guide/SKILL.md`.
- **5g** â†’ League History default emptied + fetch gated (see the deferred line above).
- **Step 6** â†’ four `GUIDE.md` files (`betting/`, `fantasy/`, `fantasy/seasonal_projections/`,
  `fantasy/dfs/`), first-person, 1,500â€“2,500 words, seasonal one scanned against the board fence.

- **5f location correction (2026-07-12):** Joseph moved the `subproject-guide` skill from the repo's `.claude/skills/` to the workspace-level `cowork_OS/.claude/skills/subproject-guide/SKILL.md` (applies across all repos there); no copy remains in this repo.
