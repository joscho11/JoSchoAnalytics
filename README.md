# JoScho Analytics

JoScho Analytics is a source-available Streamlit site for football and basketball analysis, fantasy projections, and league-history research. This public repository contains the site, validated release artifacts, and evaluation evidence. Model training and private source data live in separate producer repositories.

**Live site:** [joschoanalytics.streamlit.app](https://joschoanalytics.streamlit.app)

## Current site

The app has 14 routes, grouped in the navigation as Betting, Fantasy, College Basketball, and More:

| Route | Purpose |
|---|---|
| Home | Site status and product links. |
| This Week | Upcoming NFL slate and weekly context. |
| Weekly Predictions | NFL spread predictions, market comparisons, and release status. |
| Touchdown Props (Beta) | Anytime and first-touchdown comparisons with posted prices. |
| Track Record | Graded spread results and historical comparisons. |
| Season Totals (Beta) | NFL team win projections compared with posted totals. |
| Weekly Fantasy (Beta) | Weekly player projections and postgame grading. |
| DFS Optimizer (Beta) | DraftKings Classic lineup builder using checked projection files. |
| Draft Board | 2026 season projections, market ranks, and descriptive talent context. |
| Rookie Board | Rookie hit probabilities, projections, college production, and athletic context. |
| Daily predictions (Beta) | College basketball score predictions and exploratory market comparisons. |
| Film Room | Short video breakdowns with written analysis. |
| League History | Sleeper, ESPN, and Yahoo league records and manager trends. |
| Help & Guide | Plain-language product methods, definitions, and limitations. |

The checked-in manifest was last updated October 27, 2026. It points to active 2026 spread and fantasy builds for Week 8, with Week 7 as the latest grading pointer for both. The touchdown release manifest also includes Week 8. For live status, use the manifest files and `python -m publishing.cli status`; weekly status changes more often than this README.

The College Basketball page and release contract are implemented, but this checkout contains no published daily card manifest, so a released card was not verified locally.

## Models and evidence

The current spread product uses the Sunday-to-Tuesday market Ridge, model version `spread-v3-prod-sunday-tuesday-market-actual-starter-0c213b99e845`. Its current historical benchmark is a 2021–2025 chronological walk-forward: 251 wins and 186 losses among 437 graded HIGH picks, with 9 pushes among 446 labels (57.44% ATS; one-sided 95% Wilson lower bound 53.51%). Tuesday US median lines select HIGH at a 3-point threshold; the best captured Tuesday quote is used for display and grading. This measures historical Tuesday line performance, not closing-line value, and does not establish future profitability or a proven edge.

The older 64.2% headline was retracted after a pregame feature leak. The corrected archived in-repository HIGH book is 129/238 (54.20%; Wilson lower bound 47.86%), below the roughly 52.4% break-even rate at -110. The old result and the 2026 walk-forward are different evidence sets; neither supports claiming a guaranteed or proven betting edge. See the [betting guide](betting/GUIDE.md) and [Track Record](https://joschoanalytics.streamlit.app/track-record) for methods and graded evidence.

Weekly fantasy, spread predictions, and touchdown boards are released from producer candidates through `publishing/`. Validators check contracts and hashes before builds are activated. Grading is stored separately from the original prediction or projection. The site reads CSV and JSON artifacts; it does not load serialized model files.

## Repository map

| Path | Contents |
|---|---|
| `app.py`, `site_pages/` | Streamlit entrypoint and lazily loaded routes. |
| `publishing/` | Candidate validation, immutable releases, manifests, grading, rollback, and CLI. |
| `data/releases/` | Published builds, active pointers, and grading results. |
| `betting/`, `fantasy/`, `futures/` | Display rules, frozen/demo data, and published product artifacts. |
| `film_room.py`, `video_content.py`, `video_breakdowns/` | Film Room registry and scripts. |
| `tests/`, `.github/workflows/` | Offline tests, visual checks, CI, and scheduled release maintenance. |
| `docs/` | Product contracts, historical plans, and editorial drafts. |

See [AGENTS.md](AGENTS.md) before changing production data paths. The [documentation index](docs/README.md) points to current guides and labels historical material.

## Run locally

```bash
git clone https://github.com/joscho11/JoSchoAnalytics.git
cd JoSchoAnalytics
python -m venv .venv
pip install -r requirements.txt
streamlit run app.py
```

For offline tests, install `requirements-test.txt`, set `APP_OFFLINE=1`, then run:

```bash
python -m pytest tests/test_site_nav.py tests/test_public_boundary.py -q
```

The visual suite uses Playwright and Chromium. See [visual test instructions](tests/visual/README.md); screenshot baselines should be refreshed only for intentional visual changes using the documented Linux Chromium environment.

## License

This repository uses the [PolyForm Noncommercial License 1.0.0](LICENSE). You may read, modify, and use the code for noncommercial work. Commercial use requires a separate license.

Copyright © 2026 Joseph Schoenbaum.
