# Design proposal — daily ADP refresh for the 2026 Draft Board (2026-07-13)

**For approval before any workflow/automation is created.** The model is FROZEN; this pipeline
refreshes Sleeper ADP only and recomputes the price-derived columns against the frozen artifacts.
It never writes `phase4_band_2026.csv`, `talent_index_2026.csv`, the season dataset, or
`sleeper_adp_2020_2026.csv`. Captured as the `board-refresh` skill (`.claude/skills/board-refresh/`).

## The freeze boundary (established from the code)

`apply_board_labels.py` defines `value_gap = adp_pos_rank − sleeper_pos_rank`, where
`sleeper_pos_rank` is the FROZEN projection rank. The band (P10–P90, P(top-12/24), bust) is a
function of the projection rank only — **ADP-independent**. So refreshing ADP changes exactly three
columns and nothing else:

| Column | Source on refresh |
|---|---|
| `adp_half_ppr` (price) | fresh Sleeper pull |
| `adp_pos_rank` (within-position price rank) | recomputed over the frozen 180-player pool |
| `value_gap` | `new adp_pos_rank − frozen projection rank`, where **frozen projection rank = frozen `adp_pos_rank` − frozen `value_gap`** (both read from the frozen band; ADP-independent) |

Everything else the board shows (estimate, bands, probabilities, populations, `signal_status`,
talent) is read read-only from the frozen artifacts.

## a. The refresh script — `refresh_board_adp.py`

Reuses existing logic, does not fork it:

1. `players = fetch_adp.load_players()`; `fresh = fetch_adp.fetch_season(2026, players)` — the exact
   existing endpoint/parse code. **Read-only w.r.t. disk** (I call the functions, I do not call
   `fetch_adp.main()`, so `sleeper_adp_2020_2026.csv` is never overwritten).
2. Read `phase4_band_2026.csv` **read-only** → the 180 rows with `player`, `position`, `player_id`,
   frozen `adp_pos_rank`, frozen `value_gap`. Compute `proj_pos_rank = adp_pos_rank − value_gap`.
3. Bridge `fresh` → the 180 by `norm_name + position` using the same `_utils.norm_name` + the
   shared `ALIAS` table `apply_board_labels.py` uses (Gainwell etc.). Attach fresh `adp_half_ppr` to
   each band row's `player_id`.
4. For each of the 180: `adp = fresh price if matched in a healthy pull, else the frozen price`
   (per-player fallback keeps the overlay complete and stateless — no partial file ever).
5. Deterministic recompute over all 180: sort by `(adp, player_id)`, then
   `adp_pos_rank = groupby(position).rank(method="first")`; `value_gap = adp_pos_rank − proj_pos_rank`.
6. **Write exactly one file:** `board_adp_live_2026.csv` (regenerable) with columns
   `player_id, adp_half_ppr, adp_pos_rank, value_gap, refreshed_at`. Written atomically (temp file →
   `os.replace`).

**Frozen files read:** `phase4_band_2026.csv`, `season_dataset_2014_2026.csv` (for the frozen ADP
fallback), `talent_index_2026.csv` untouched entirely. **Frozen files written:** none.

`draft_board_2026.py` change (dashboard code, not a frozen artifact): LEFT-JOIN the overlay by
`player_id` and prefer its three columns when present; fall back to the frozen band's
`adp_pos_rank`/`value_gap` and the season-dataset `adp_half_ppr` when the overlay is absent — so a
fresh clone and the hermetic AppTest both render.

## b. Freshness / idempotency

Deterministic: the same ADP snapshot → byte-identical overlay. Ranks use a fixed sort key
`(adp_half_ppr, player_id)` before `rank(method="first")`, so ties never depend on input order.
`refreshed_at` is the **pull date** (not a timestamp), so two runs on the same day produce an
identical file. Safe to run repeatedly.

## c. The auto-stamped caption

`draft_board_2026.py` currently hardcodes:
`"Draft prices are Sleeper ADP as of July 10, 2026; prices move as real drafts happen."`
Replace the date with the overlay's `refreshed_at`, in first-person voice, licensed wording
unchanged (this is descriptive caption text, not a licensed label):
`f"I refresh these draft prices from Sleeper ADP — latest pull {refreshed_at}. Prices move as real drafts happen."`
Falls back to the current static wording if the overlay is absent. It is a live product surface, so
it goes through the forbidden-language scan before shipping (no buy/sell/fade/tier/valued/accuracy
terms — the proposed text is clean).

## d. Failure behavior (never publish a broken board)

- The script **validates the pull before writing**: abort (exit non-zero, write nothing) if the
  fresh frame is empty, malformed, or has fewer than a floor of skill players with ADP
  (proposed floor: **150**; healthy 2026 pulls return several hundred).
- A healthy pull missing a specific one of the 180 → that player falls back to the frozen ADP for
  the run (no abort, overlay stays complete).
- The workflow's **commit step is gated on `success()`** (as in `weekly_predictions.yml`), so an
  aborted run pushes nothing and the **last-good `board_adp_live_2026.csv` stays committed and
  live**. The board is never partial or empty.

## e. Cron schedule + one-line-tunable cadence

**Recommended default: daily**, `cron: '0 13 * * *'` (13:00 UTC = 9am ET during EDT). Cadence is the
single cron line — weekly = `'0 13 * * 2'`, weekdays = `'0 13 * * 1-5'`.

**Reasoning (and why I diverge slightly from the weekly-through-August lean):** ADP moves fastest as
draft volume ramps through August, and a weekly cadence can leave a 6-day-stale price on the board
during exactly that ramp. Daily is operationally trivial (a ~30-second ADP pull + a small CSV
write) and keeps the board never more than a day stale across the whole Aug–Sept draft window. A
two-phase weekly→daily schedule would need either two cron entries or date-gating for a benefit
daily already covers essentially for free. One honest caveat that cuts the other way: after the
Week-1 kickoff (~Sept 10) the pre-draft board is stale-by-nature — most drafts are done — so the
right move then is to **pause** the workflow (disable it) rather than keep refreshing, not to run it
daily into the season. I recommend: daily now through the opener, then disable.

## f. What the workflow commits, as whom, and CI interaction

- Commits **only** `fantasy/seasonal_projections/board_adp_live_2026.csv`, as `github-actions[bot]`
  (same identity as `weekly_predictions.yml`), message `Board ADP refresh <date>`.
- Each commit to `main` triggers `test.yml`, including the new **deploy-parity** job and
  `test_app_draft_board.py` — so every refresh is smoke-tested by a full board render before it's
  trusted. No circular trigger: the refresh workflow is cron/dispatch-only, not push-triggered.
- Streamlit Cloud auto-redeploys on the push and loads the fresh overlay. Daily is the practical
  ceiling to avoid redeploy churn; a failed run pushes nothing, so a bad pull never redeploys a
  broken board.

## Files this build will touch (on approval)

- **New:** `fantasy/seasonal_projections/refresh_board_adp.py`; `.github/workflows/board_refresh.yml`
  (schedule + `workflow_dispatch`); `fantasy/seasonal_projections/board_adp_live_2026.csv` (first
  regenerable output).
- **Modified:** `draft_board_2026.py` (overlay LEFT-JOIN + fallback + auto-stamped caption).
- **Never touched:** `phase4_band_2026.csv`, `talent_index_2026.csv`, `season_dataset_2014_2026.csv`,
  `sleeper_adp_2020_2026.csv`, and every hash-pinned artifact.

**STOP — awaiting approval of this design before creating the workflow or any automation (step 4).**
