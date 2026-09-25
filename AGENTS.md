# AGENTS.md

Guidance for coding agents in this repository.

## What this repo is

JoSchoAnalytics is the public Streamlit website plus immutable release artifacts.
Training, notebooks, serialized models, and DFS projection generation live in
private producer repos. The public DFS Optimizer page uses a reviewed vendored
runtime and checked or user-supplied CSV artifacts; it does not generate projections.

**Live site:** https://joschoanalytics.streamlit.app

Private producers:

- `spread_v3_prod` writes weekly spread candidates
- `weekly_projections_v2_prod` writes weekly fantasy candidates
- `dfs_optimizer_v1_prod` writes verified direct-DK projection candidates
- `td_count_model_beta` writes 2025 Anytime TD demo CSVs into `betting/anytime_td/`
- Guide: `betting/anytime_td/GUIDE.md`
- 2026 Anytime TD book Yes is a manual T-3h paste from Joseph; for Sunday slates,
  expect that handoff early Sunday morning before kickoff. Do not call the Odds API
  for live weeks.

This repo validates candidates in `publishing/`, stores them under `data/releases/`,
and renders pages from those files plus frozen demo CSVs.

## Commands

```bash
pip install -r requirements.txt
streamlit run app.py
```

```bash
pip install -r requirements-test.txt
set APP_OFFLINE=1
python -m pytest tests/test_public_boundary.py tests/test_site_nav.py tests/test_publishing_pipeline.py tests/test_visual_regression.py -m "not visual" -q
python -m publishing.cli status
```

Page screenshots (Playwright + Chromium). Copy and overflow checks run everywhere.
Committed PNGs are Linux Chromium only. Refresh them only for an intentional visual
change, from ubuntu-latest (or WSL with the same Playwright 1.62 Chromium):

```bash
python -m playwright install chromium
pytest tests/test_visual_regression.py --update-visual
```

## Layout

| Path | Role |
|---|---|
| `app.py` | Streamlit entrypoint |
| `site_pages/` | One module per page |
| `publishing/` | Candidate validation, immutable releases, grading |
| `data/releases/` | Published builds and the active manifest |
| `betting/` | 2026 HIGH rules, graded trackers |
| `fantasy/` | Draft, rookie, talent, and 2025 demo CSVs |
| `futures/published/` | Season Totals artifacts |
| `draft_board_2026.py` | Draft Board, CSV-only |
| `tests/test_public_boundary.py` | Fails if modeling files or ML imports return |

## Rules

- Site pages read CSV/JSON artifacts. They do not load `.pkl` files.
- Do not restore `archive/`, notebooks, training scripts, or DFS projection-generation source.
- Keep the public DFS page on the reviewed vendored runtime and direct-DK CSV contract.
- Keep HIGH at a 3.0-point Tuesday leftover. Do not claim CLV. Do not cite the retracted 64.2% or 192/336 as current.
- The promoted QB-retaining Sunday-to-Tuesday market Ridge with team-scoped injured-reserve starters and an automatic uncertain-QB flag has 46 core features and 49 fitted inputs. It was refitted on 2026-09-24 after a price-median units fix (eight training rows had impossible moneyline medians; medians are now taken on the decimal scale), bundle `f4f09df27683`. Its 2021-2025 walk-forward benchmark is 246/430 = 57.21% ATS, 11 pushes among 441 HIGH labels, Wilson lower 53.25%, graded at the best US Tuesday quote (`betting/market_model_benchmark_v5.json`; v4, v3 and v2 are history). The previous bundle scored 256/432 = 59.26%, Wilson lower 55.32%; the new record is lower and the difference is not statistically established either way. Never cite 256/432 as the current record. Five general injury features and vacated snaps were removed; four QB features remain; `ir_starters_diff` (home minus away non-QB starters on regular IR, from each team's previous-game roster, counting only snaps for the listing team) and the two `qb_uncertain_*` flags are the added inputs. Manual QB scenarios on the card are not a model input. The Tuesday US median drives model input, pick, edge, and HIGH qualification; the best quote drives display, execution, and grading. A market move alone cannot add HIGH, but a validated model-version correction may change HIGH labels at the same frozen line. Do not move qualification onto the shopped quote. Never claim CLV.
- The archived corrected in-repo spread audit is 129/238 = 54.20%; it is not the live 2026 claim.
- Draft Board copy must not name the 75/25 Sleeper mix.
- After any page change, run AppTest on the affected pages with `APP_OFFLINE=1`.
- After a layout or copy change on a public page, run `pytest tests/test_visual_regression.py`. Use `--update-visual` only for an intentional screenshot change.
