# Streamlit Community Cloud throttling — measured diagnosis (2026-07-29)

Third pass at recurring CPU throttling on <https://joschoanalytics.streamlit.app> (branch
`main`), after `74d1ad7` (2026-07-24) and `c5a10ec` (2026-07-28) both reduced real app cost
and throttling still recurred.

**Conclusion up front: the deployed application's CPU cannot cause this.** A complete
production visit to all nine pages costs **2.53 CPU-seconds** and peaks at **218 MB RSS**;
the idle server burns **~10 CPU-seconds per hour**. Community Cloud's documented floor is
0.078 cores — 281 CPU-seconds per hour — so the whole site is under 1% of the *minimum*
guaranteed allocation. Every app-side hypothesis I could test came back negative. What
remains is either platform-side scheduling/accounting on shared Community Cloud capacity,
or live traffic that Streamlit's public analytics does not count. Telemetry to separate
those two is now in the app, off by default.

---

## 1. Method

Two harnesses, both committed and re-runnable:

| Harness | What it measures |
|---|---|
| `scripts/bench_pages.py` | Per page, in a **fresh interpreter**: CPU (user+sys, whole process), wall, peak RSS, module count + which heavy packages loaded, Streamlit cache cardinality and retained bytes, and every outbound TCP connect. Cold and warm (`--warm N`). `--walk` runs all nine pages in **one** process — the real single-container case. `--online` lifts the offline guard so real egress is counted. |
| `scripts/bench_server.py` | The **real `streamlit run` process**: boot-to-HTTP-200 CPU, then two idle windows with no client, a static GET, and the watched-source-file count. This is the only way to see steady-state cost, which AppTest cannot show. |

**Environment parity matters and changed the numbers.** `.venv-test` carries `matplotlib`
transitively via `catboost`; `requirements.txt` does not. `pandas.io.formats.style` does
`try: import matplotlib` (guarded — `has_mpl = False` without it), so `DataFrame.style`
works either way, but any env with matplotlib **overstates** the Draft Board's cold cost by
~0.27 CPU-s and ~25 MB. All headline numbers below come from a throwaway venv containing
**exactly `requirements.txt` + pytest + psutil** (matplotlib absent, confirmed). Python
3.11 locally vs 3.12 on Cloud (`runtime.txt`).

---

## 2. Measurements

### 2.1 Per page, fresh process, requirements.txt parity

| Page | import CPU | cold CPU | cold wall | warm CPU | peak RSS | cache | net |
|---|---|---|---|---|---|---|---|
| `app` (default landing) | 0.27 | 0.55 | 1.03 | 0.042 | 137.7 MB | 0.05 MB | 0 |
| Weekly Predictions | 0.36 | 0.55 | 0.59 | 0.047 | 133.9 MB | 0.05 MB | 0 |
| Track Record | 0.38 | 0.53 | 0.65 | 0.047 | 138.9 MB | 0.05 MB | 0 |
| **Draft Board** | 0.31 | **0.77** | 0.83 | 0.047 | **145.7 MB** | 0.08 MB | 0 |
| Rookie Board | 0.36 | 0.52 | 0.59 | 0.026 | 138.5 MB | 1.62 MB | 0 |
| Weekly Fantasy | 0.33 | 0.66 | 0.70 | 0.031 | 137.6 MB | 0.14 MB | 0 |
| DFS Optimizer | 0.34 | 0.16 | 0.20 | 0.000 | 78.0 MB | 0 | 0 |
| Film Room | 0.27 | 0.20 | 0.24 | 0.005 | 72.7 MB | 0 | 0 |
| League History | 0.33 | 0.58 | 0.63 | 0.000 | 133.4 MB | 0 | 0 |
| Help & Guide | 0.38 | 0.42 | 0.53 | 0.010 | 127.6 MB | 0.03 MB | 0 |

Seconds. Zero network on every page with `APP_OFFLINE=1` — the hermetic guard holds.

### 2.2 One process, all nine pages (the container's real life)

| | offline | **online (production paths live)** |
|---|---|---|
| total CPU, 9 pages | 1.95 s | **2.53 s** |
| peak RSS | 157.5 MB | **218.4 MB** |
| final cache | 16 entries / 1.86 MB | 17 entries / 2.21 MB |
| egress | none | GitHub (nflverse parquet) + Google (GA beacon) |

Warm reruns after the first visit: **0.05–0.14 s wall, 0.05–0.11 s CPU per page.**

### 2.3 The real server process

| | value |
|---|---|
| boot → HTTP 200 | **1.56 s wall / 0.63 CPU-s / 80.9 MB RSS** |
| idle, window 1 (180 s) | 0.44 CPU-s → **8.75 CPU-s/hour** |
| idle, window 2 (180 s) | 0.55 CPU-s → **10.94 CPU-s/hour** |
| static GET of `/` | 0.025 s wall, ~0 CPU, 6,602 bytes |
| watched source files | 22 files across 5 directories |

Idle cost is **~0.3% of one core** and did not change materially with
`--server.fileWatcherType` set to `none`, `poll`, or `watchdog` (7.5 / 6.6 / 14.1 and
19.7 / 5.6 / 9.4 CPU-s/hr across two windows each — the spread is sampling noise, not
signal). `watchdog` is a hard Streamlit dependency on non-macOS, so Cloud gets the
event-based watcher, not polling. **The file watcher is not a factor.**

### 2.4 Documented platform limits (Streamlit docs, retrieved 2026-07-29)

CPU **0.078 cores minimum, 2 cores maximum**. Memory **690 MB minimum, 2.7 GB maximum**.
Storage ≤ 50 GB. "If your app meets or exceeds its limits, it may slow down from
throttling or become nonfunctional." Apps with no traffic for 12 hours hibernate.
Limits are shared by all Community Cloud users and "may change at any time without notice."

**Against the floor:** the whole nine-page site is 2.53 CPU-s. One CPU-hour at the 0.078-core
floor is 281 CPU-s. The site is **0.9% of the minimum hourly allocation**, and peak RSS is
**32% of the 690 MB memory floor**. Idle 24 h ≈ 240 CPU-s ≈ **3.6% of a floor-rate day.**

---

## 3. Audits — all negative

### Caches (task 4)
Every cached function after walking all nine pages in one process:

| function | entries | bytes | max_entries | ttl |
|---|---|---|---|---|
| `page_rookie_board._load_college_wr` | 1 | 744,759 | — | 3600 |
| `page_rookie_board._load_college_rb` | 1 | 421,814 | — | 3600 |
| `page_rookie_board._load_college_te` | 1 | 286,623 | — | 3600 |
| `page_rookie_board._load_college_qb` | 1 | 157,761 | — | 3600 |
| `page_weekly_fantasy._load_proj_csv` | 1 | 111,300 | — | 3600 |
| `page_rookie_board._load` | 3 | 65,694 | — | 3600 |
| `draft_board_2026._load_outside_market_players_cached` | 1 | 48,118 | — | none |
| `draft_board_2026._load_board_2026_cached` | 1 | 38,505 | — | none |
| `dashboard_data.load_predictions` | 1 | 31,871 | — | 300 |
| `page_rookie_board._load_proj` | 1 | 27,150 | — | 3600 |
| `dashboard_data.load_totals` | 1 | 16,319 | — | 300 |
| 4 more (`_refresh_date`, `_compute_hc_stats`, `_projection_pool_size_cached`, +1 online) | 1 each | < 200 each | — | — |

- **No unbounded key space.** Every key is a file fingerprint, a season, or a draft class.
  `max_entries=None` is safe here because the key domains are finite and tiny (the two that
  *aren't* — `_sleeper_get` and `_fetch_sleeper_history` — already carry explicit 128/8 caps
  from `74d1ad7`).
- **No large retained object.** 2.21 MB total, worst single entry 745 KB. The one big
  production object, the nflverse season pull, is column-trimmed to 14 of 145 columns
  *before* caching, so it lands as ~0.35 MB with `max_entries=4`.
- **No cross-session duplication.** `st.cache_data` is process-global; nothing is
  session-scoped. `cache_resource` is unused entirely.
- **TTL churn is real but negligible — I measured it rather than assuming.** Re-running
  every TTL-expiring body: `load_tracker` 0.78 ms, `load_totals_tracker` 0.78 ms,
  `_compute_hc_stats` ~0 ms (there is exactly **one** `agent_analysis_*.json`, 12 KB),
  `_load_board_2026_cached` 43.75 ms, `_load_college_wr` 6.25 ms,
  `_board_source_fingerprint` 0.94 ms for its 32 `stat()` calls. Total worst case if every
  TTL expired at once: **~55 ms.** These are local files that change only on redeploy, so a
  fingerprint key would be tidier than a TTL — but **the measurement does not justify
  touching working cache code**, so I did not. Recorded here so it isn't re-investigated.

### Session behavior and reruns (task 5)
- Zero occurrences of `st.rerun`, `experimental_rerun`, `st_autorefresh`, `run_every`,
  `st.fragment`, `while True`, `threading` (before this change), or a query-param write in
  any runtime module. Confirmed by grep across the whole runtime surface.
- Page navigation costs one script run of `app.py` + the selected module. That is
  Streamlit's execution model, not a defect; **measured at 0.05–0.14 s wall warm.** Non-selected
  pages are lazily imported (`_lazy_render`), enforced by
  `test_site_nav.py::test_nonselected_pages_are_lazy_imported`.
- A browser reconnect that creates a new session repeats exactly one cold-ish render plus
  one GA beacon (`site_pageview_once` is session_state-gated). Nothing accumulates:
  `--walk` shows RSS flat at ~151 MB and the cache at 16 entries after the first pass over
  every page.
- The only concurrency in the app is League History's 6-worker matchup pool, which fires
  only behind an explicit Load submission and a 15–20-digit plausibility gate.

### What the container carries vs what the app reads
Instrumented every `open` and `pd.read_csv` across all nine pages:
**32 non-code files, 4.54 MB, plus 7 repo `.py` files, 160 KB.** The container carries a
**266–293 MB** checkout (full clone 292.6 MB / 102.7 MB `.git`; shallow 266.0 MB / 76.1 MB
`.git`; clone wall 19.1 s full, 10.4 s shallow) to serve 4.7 MB. Dependency install is
**48.6 s and 600 MB** of site-packages, and only reruns when `requirements.txt` changes
(once since 2026-07-28). Dropping `nflreadpy` + `polars` would save 195 MB and 7.6 s — but
they are the Weekly Fantasy actual-stat path, so they stay.

---

## 4. Push / rebuild correlation (task 6) — and what it does NOT show

Every push to the deployed branch restarts the app. Push events reaching `main` in the 24 h
after `c5a10ec`, with what each actually shipped:

| when (UTC) | commit | new blob MB | pack MB | pack wall |
|---|---|---|---|---|
| 2026-07-28 15:15 | `0c2e35f` Board ADP refresh (bot) | 0.01 | 0.01 | 0.03 s |
| 2026-07-28 15:19 | `c5a10ec`+`fdad888` throttle fix | 0.16 | 0.06 | 0.03 s |
| 2026-07-28 16:51 | `aa378ff` project sweep | 0.94 | 0.20 | 0.05 s |
| 2026-07-29 02:12 | `787486c` **hc/oc research features** | **41.75** | **9.85** | 0.90 s |
| 2026-07-29 15:07 | `1b7b36f` Board ADP refresh (bot) | 0.01 | 0.01 | 0.03 s |
| 2026-07-29 15:28 | `9fe8507`+`0eac69c` hc/oc | 3.13 | 0.82 | 0.17 s |

**Measured, not assumed: deployment churn is not a CPU driver.** The git side of the
heaviest push is 9.85 MB and 0.9 s; six of the eight pushes are under 1 MB packed. Charging
every restart the full boot cost plus a complete cache re-warm gives
8 × (0.63 + 1.95) ≈ **21 CPU-seconds per day — 0.3% of a floor-rate day.** The
`787486c` outlier is `fantasy/projections/coaching/data/wikipedia_team_season_cache.json`
(39.65 MB tracked), a research artifact the live app never opens.

**The correlation the task asks for cannot actually be computed from available evidence, and
I am not going to imply otherwise.** No artifact I can read records a throttle window:
Community Cloud's per-app resource history is not exposed, the app logs are only visible
live in "Manage app", and nothing in the repo timestamps a banner. I have push timestamps on
one axis and nothing on the other. A direct probe on 2026-07-29 21:0x UTC found the app
healthy — `HTTP 200` in 1.39 s after 3 redirects through `share.streamlit.io/-/auth/app`,
serving the normal 5,843-byte shell, no hibernation or resource-limit page — matching the
spot check. **The telemetry in §6 is what makes this correlation computable next time.**

---

## 5. Production isolation (task 7) — recommend the branch, reject the other two

| Option | Measured effect | Verdict |
|---|---|---|
| **`streamlit-prod` branch** | Restarts fall from ~8/day to ~1–2/week: 6 of the last 8 pushes touched only `fantasy/projections/coaching/**`, which the app never imports. CPU saved ≈ 21 CPU-s/day = **0.3% of a floor-rate day — not a CPU fix.** The real gain is measured latency exposure: a visitor landing on a cold process pays **1.03–1.36 s** first render vs **0.06–0.14 s** warm, a 10–20× difference, and ~85% fewer restarts cuts that exposure proportionally. Plus blast radius: `main` took 41.75 MB of unrelated research blobs on 2026-07-29. | **Recommended**, on availability and blast-radius grounds only. Cost: one Cloud setting + merge discipline, zero code. |
| Separate lightweight repo | Would cut the checkout from 266–293 MB to under 10 MB (the app reads 4.7 MB). But storage caps at 50 GB, so **288 MB of disk buys nothing measurable**, and it costs a sync job, duplicated shipped artifacts, and contradicts the footer's public-repo promise. | **Reject** — not supported. |
| External ADP overlay fetch | The bot commit is the **smallest** of the eight pushes (0.01 MB packed, 5 objects, 0.03 s) and 1 of 8, while research pushes are 6 of 8. Trades a 7.6 KB local read for a live network dependency on the board's critical path, and does not touch the actual churn. | **Reject** — not supported. |

`git branch streamlit-prod main` now exists locally (pointer only, no checkout, working tree
untouched; `git branch -d streamlit-prod` reverses it). Two manual steps remain, both yours:
push the branch, and repoint the app in the Cloud dashboard.

**One trap if you adopt it:** `.github/workflows/board_refresh.yml` commits and pushes
`board_adp_live_2026.csv` to whatever branch it checked out — `main`. Point the deployed app
at `streamlit-prod` without changing that and **the live board silently stops refreshing.**
The workflow needs either a `ref: streamlit-prod` checkout or a second push target. I have
not edited it, because the branch is not in use yet.

---

## 6. Changes made

Two, both supported by measurement, neither touching a model, prediction, tracker, or
public statistical claim.

**`runtime_telemetry.py` (new) + two lines in `app.py`.** Records process start, per-process
script-run count, a per-process session ordinal, selected page, process CPU delta, wall
time, RSS and peak RSS, one JSON line per run to stderr with prefix `JSA_TELEMETRY` — the
Cloud app log is the only durable sink on an ephemeral container. **Off unless
`APP_TELEMETRY = "1"`** as an env var or a Cloud Secret, so deployed behavior is unchanged
until you flip it. **Zero new dependencies** (`resource` / `os.times` / `/proc/self/statm`),
which keeps `requirements.txt` at eight packages. **No personal data** — no IP, user agent,
referrer, query string, cookie, or any stable visitor identifier; a test asserts the
forbidden field names never appear. Measured overhead: **6.7 µs per script run enabled,
0.9 µs disabled** — after resolving platform capability once at import instead of per call,
which cut it from 922 µs (swallowed exceptions on non-Linux dominated the cost).
Removal is this file plus the `begin()`/`end()` pair.

*This is the instrument that settles the open question.* If a throttle recurs and the log
shows a handful of runs, the cause is platform-side. If it shows thousands — crawlers,
health probes, reconnect storms — the cause is uncounted traffic, and Streamlit's "2 views"
was never measuring the right thing.

**GA beacon off the first-render critical path** (`dashboard_chrome.send_ga_event`). It was a
synchronous `requests.post` with `timeout=3` running inside `site_pageview_once()` *before*
`st.navigation`, so the first render of **every** session waited on it. Measured round trip
to `google-analytics.com/mp/collect`: **223.6 ms mean, 234.6 ms max over 5 attempts**, with
3 s allowed in the tail. It is a fire-and-forget beacon — nothing on the page reads the
response — so the POST now goes on a one-shot daemon thread. Endpoint, params, payload and
timeout are byte-identical; every `session_state` read still happens on the script thread; a
thread-creation failure falls back to the old inline call. Not a persistent worker.
`tests/test_runtime_telemetry.py::test_ga_beacon_does_not_block_the_render` stubs a 2.0 s
POST and asserts `send_ga_event` returns in **< 0.3 s** while the beacon still goes out.

**Deliberately NOT changed:** the caches (measured churn ≈ 55 ms worst case — no
justification), `_load_actual_stats_season`'s TTL (that one is genuinely live data),
`requirements.txt`, and the board-refresh workflow.

---

## 7. Validation

- Exact deploy-parity list under a **requirements.txt-only venv**: `tests/test_dashboard_utils.py`,
  `test_app_draft_board.py`, `test_site_nav.py`, `test_board_page.py`, `test_betting_pages.py`,
  `test_fantasy_league_pages.py`, `test_help_page.py`, `test_model_explanations.py` → **59 passed.**
  (The prior entry's "51" is the same list before tests were added since 2026-07-28; the
  suite grew, nothing was skipped.)
- Same list plus the runtime suites CI omits (`test_app_talent_columns.py`,
  `test_page_rookie_board.py`) plus the new `test_runtime_telemetry.py` → **74 passed.**
- All nine pages: `test_site_nav.py::test_every_page_renders_offline_clean` → **pass**;
  and the harness renders all nine with **0 exceptions / 0 errors** in every run above.
- Before/after, parity env: total walk CPU **1.906 s → 1.953 s**, peak RSS
  **157.8 MB → 157.5 MB** — no regression (expected: telemetry is off, the GA change is
  online-only).
- Working tree preserved: only `app.py` and `dashboard_chrome.py` modified, only
  `runtime_telemetry.py`, `scripts/bench_pages.py`, `scripts/bench_server.py`,
  `tests/test_runtime_telemetry.py` added. `fantasy/projections/coaching` + `preregs` still
  show exactly the 22 modified / 37 untracked paths they had at session start. Nothing
  staged, nothing committed.

---

## 8. Remaining uncertainty — stated plainly

1. **The cause is not established.** I ruled the application out with numbers; I did not
   prove what the platform is doing. Two live hypotheses remain: (a) shared-tenancy
   scheduling near the 0.078-core floor, which would make "throttling" a platform condition
   the app cannot influence; (b) uncounted traffic (crawlers, probes, reconnects) driving
   script runs that Streamlit's viewer analytics never reports. **§6's telemetry
   discriminates between them.** Do not ship another "throttle fix" before reading it.
2. **No throttle-window timestamps exist**, so §4's correlation is one-sided by necessity.
   Next occurrence: capture the Cloud log window and the banner time, then join on the
   `JSA_TELEMETRY` `boot`/`run` lines.
3. **Platform-vs-app is my read, not a proof.** The docs say limits "may change at any time
   without notice" and are shared across all Community Cloud users; nothing exposes per-app
   CPU accounting.
4. **Local measurement is Windows / Python 3.11**; Cloud is Linux / 3.12. Absolute CPU will
   differ. The ratios (cold vs warm, idle vs active, app vs quota floor) are what carry, and
   they carry by three orders of magnitude.
5. **The 12-hour hibernation is a confound I could not separate.** With two lifetime views
   this app is asleep most of the time, and a wake-from-hibernation cold start is slow in a
   way that is indistinguishable from throttling to a visitor. Push-driven restarts may be
   the only thing keeping it awake — which would mean isolating production *increases*
   hibernation exposure. Worth watching after any branch switch.
6. **If it recurs with telemetry showing near-zero runs, the honest move is to stop
   optimizing.** Three passes have now cut real cost, and the remaining app cost is 0.9% of
   the minimum hourly allocation. There is nothing left to win app-side; the answer would be
   a host with reserved capacity — the same conclusion `74d1ad7`'s note reached, now with
   numbers behind it.

## Re-running any of this

```bash
# fresh-process per-page benchmark (cold + 3 warm), JSON out
python scripts/bench_pages.py --warm 3 --json bench.json
python scripts/bench_pages.py --walk            # all nine pages, ONE process
python scripts/bench_pages.py --walk --online   # production paths live, egress counted
# the real server: boot cost + two idle windows + watched-file count
python scripts/bench_server.py --idle 180
python scripts/bench_server.py --idle 180 --watcher none
```
Run them against a venv holding **only `requirements.txt`** (plus pytest/psutil), or the
Draft Board and Weekly Fantasy numbers come out ~0.27 CPU-s and ~25 MB too high.
