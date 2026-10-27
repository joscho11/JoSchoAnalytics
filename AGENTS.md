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
- The promoted Sunday-to-Tuesday market Ridge has 44 core features and 47 fitted inputs: actual-starter QB features (trained on the passer who took the game's first dropback, strictly as-of stats), team-scoped injured-reserve starters (`ir_starters_diff`), a net two-sided special-teams EPA feature, and no uncertain-QB flag (contract `sunday_tuesday_market_qb_ir_actual_starter_44_plus_missing_flags`, bundle `0c213b99e845`, report `betting/market_model_benchmark_v7.json`; v6 and earlier are history). Its 2021-2025 walk-forward benchmark is 251/437 = 57.44% ATS, 9 pushes among 446 HIGH labels, Wilson lower 53.51%, graded at the best US Tuesday quote. The previous bundle scored 261/449 = 58.13%, Wilson lower 54.26%; the difference is not statistically established either way, and the flag-drop test showed the variants tie within noise (253/434, 254/434, 251/437). Never cite 261/449, 246/430 or 256/432 as the current record. When a team's starting QB is unsettled, the card scores each listed QB and the official pick is the probability-weighted blend of those scores; it is HIGH only if the blended gap is 3.0 or more points and every QB with at least 25% probability is on the blended side. The per-QB paths are context only. Releases built before the 2026 Week 8 correction use the older model and old verdict values (`high_all_clear`, `high_split`, `scenario_high_only`, `no_high`); new verdicts are `blend_high`, `blend_no_high`, `blend_split_no_high`. The Tuesday US median drives model input, pick, edge, and HIGH qualification; the best quote drives display, execution, and grading. A market move alone cannot add HIGH, but a validated model-version correction may change HIGH labels at the same frozen line. Do not move qualification onto the shopped quote. Never claim CLV.
- The archived corrected in-repo spread audit is 129/238 = 54.20%; it is not the live 2026 claim.
- Draft Board copy must not name the 75/25 Sleeper mix.
- After any page change, run AppTest on the affected pages with `APP_OFFLINE=1`.
- After a layout or copy change on a public page, run `pytest tests/test_visual_regression.py`. Use `--update-visual` only for an intentional screenshot change.
