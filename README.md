# JoScho Analytics

JoScho Analytics is a source-available Streamlit site for NFL betting analysis, fantasy football projections, and league-history research. I publish the assumptions, results, and limits beside the products. This repository is the website plus checked release artifacts. Training code and serialized models live in private producer repositories.

**Live site:** [joschoanalytics.streamlit.app](https://joschoanalytics.streamlit.app)

## How to read this repo

```text
app.py                 Streamlit entrypoint and nav
site_pages/            One module per page
dashboard_*.py         Shared data loaders and chrome
publishing/            Validate a producer CSV, freeze it, grade it
data/releases/         Immutable published builds + active manifest
betting/               Spread display rules and graded trackers
fantasy/               Draft, rookie, talent, and 2025 weekly demo CSVs
futures/published/     Season Totals CSV + evidence
tests/                 Offline page tests and the public-boundary scanner
```

A page should load CSV or JSON. If a change needs a `.pkl`, it belongs in a private producer, not here.

## Website coverage

| Page | What it covers |
|---|---|
| **Home** | Site status, release timing, and links to the main products. |
| **Draft Board** | A 180-player 2026 board with independent season projections, Sleeper, ESPN, or Yahoo ADP, or Model Draft Rank order, plus positional ranks, rank gaps, and talent context. |
| **Rookie Board** | Rookie hit probabilities, season projections, college production, and athletic context. |
| **Weekly Fantasy** | Half-PPR and stat projections for QB, RB, WR, and TE. Actual results appear after games finish. |
| **DFS Optimizer** | DraftKings NFL Classic lineup builder. Upload a salary CSV plus a checked direct-DK projection file. Not a performance claim. |
| **Anytime TDs** | Live 2026 Week 1 comparison board plus the 2025 Weeks 10-17 demo. Rushing and receiving TD chances versus a manually pasted book price. For fun. Not a proven edge. |
| **Weekly Predictions** | NFL spread predictions, market comparisons, model confidence, and release status. |
| **Track Record** | Graded against-the-spread results, confidence tiers, model comparisons, streaks, and betting simulations. |
| **Season Totals** | Win projections for all 32 teams compared with posted season totals. |
| **League History** | Sleeper, ESPN, and Yahoo league records, rivalries, manager profiles, draft habits, roster production, and league-wide trends. |
| **Film Room** | Short video breakdowns with written analysis and links to the related product. |
| **Help & Guide** | Betting definitions, model summaries, feature explanations, confidence rules, and product limitations. |

## Models and publication

The site covers five published product families:

- **NFL spreads:** an independent margin estimate compared with the sportsbook line. The site separates the live 2026 record from the 2025 demo.
- **Game and season totals:** a 2025 experimental game-total demo plus a separate 32-team season-win product.
- **Weekly fantasy:** 2026 Week 1 is live from one half-PPR LightGBM and locks at each game's kickoff. Later immutable revisions preserve every started game's rows exactly. The 2025 weeks 10-17 on the page are a prior-model demo.
- **DFS optimizer:** DraftKings Classic lineups from checked direct-DK projection files. No published projection edge.
- **Anytime TDs:** a live 2026 Week 1 board plus the 2025 demo, using manually pasted US-book Yes prices. For fun. Not a proven edge.
- **Draft and rookie analysis:** season projections, market ranks, rookie hit probabilities, and descriptive NFL and college talent scores.

Live spread and weekly-fantasy producers submit candidate files to this repository. The code in `publishing/` validates schemas, coverage, timestamps, hashes, and model versions before it creates an immutable release. The site reads those releases. The grading workflow writes results without changing the original prediction.

## Codebase map

| Path | Contents |
|---|---|
| `app.py` | Streamlit entrypoint and navigation. |
| `site_pages/` | One module per visible page. |
| `dashboard_*.py`, `mobile.py`, `theme_redesign.py` | Shared data loading, UI components, responsive styles, and site chrome. |
| `publishing/` | Candidate validation, immutable releases, manifests, grading, rollback, and CLI commands. |
| `data/releases/` | Published build artifacts and the active release manifest. |
| `betting/` | Display rules, graded trackers, and Help-page calibration. |
| `fantasy/` | Published weekly, draft, rookie, and talent CSVs. |
| `futures/` | Published season-win projections and their evidence file. |
| `film_room.py`, `video_content.py`, `video_breakdowns/` | Video registry and written breakdowns. |
| `tests/` | Unit, contract, offline page-render, responsive, visual, publication, and public-boundary tests. |
| `.github/workflows/` | CI, release grading, and board market refreshes. |

Read [AGENTS.md](AGENTS.md) before changing production data paths. It documents the active sources, frozen files, and test contracts.

## Evidence and limits

Sportsbooks charge enough margin that a bettor needs about a 52.4% win rate at standard `-110` odds to break even. Backtests can overstate performance, so the site labels backtested, demo, experimental, and live results as separate evidence.

I retracted the old 64.2% spread-model claim after finding a pregame feature leak. The archived in-repo HIGH book is 129/238, or 54.2017%, Wilson lower bound 47.8551%. That result does not demonstrate an edge over break-even. The frozen 2021-2025 Tuesday benchmark, scored with injury reports legal as of Tuesday 9:00 ET, is 302/535 = 56.45% ATS at the best US Tuesday number, Wilson lower bound 52.90%. The historical tickets use a 2.5-point median-line cut; their median grade was 299/538 = 55.58%, Wilson 52.03%. Starting in 2026, the Tuesday US median drives the model, pick, edge, and HIGH flag; the chosen best US Tuesday quote is displayed separately and used for grading. The prior named cut of 3 was 246/442 = 55.66%, Wilson 51.75%. This is Tuesday line value, not closing-line value. The earlier 192/336 = 57.14% figure used same-week injury reports that postdate Tuesday and is withdrawn. The prior as-of 75/25 book was 155/290. The Track Record page shows the graded evidence used for current decisions.

The site provides research and published outputs, not paid picks or financial advice. Sports betting involves risk.

## Run locally

```bash
git clone https://github.com/joscho11/JoSchoAnalytics.git
cd JoSchoAnalytics
python -m venv .venv
pip install -r requirements.txt
streamlit run app.py
```

Streamlit serves the app at `http://localhost:8501`.

Use the test dependency set for development:

```bash
pip install -r requirements-test.txt
python -m pytest tests/test_public_boundary.py tests/test_site_nav.py -q
```

Set `APP_OFFLINE=1` when running page tests without network access. CI uses the same offline path for dashboard coverage. The Playwright job screenshots every major route at phone, tablet, and desktop widths (`pytest tests/test_visual_regression.py`). Refresh committed baselines with `--update-visual`.

## Guides

- [Betting](betting/README.md)
- [Anytime TDs](betting/anytime_td/GUIDE.md)
- [Weekly fantasy](fantasy/GUIDE.md)
- [Talent scores](fantasy/talent/README.md)
- [Rookie Board](fantasy/rookie/README.md)
- [Draft Board](fantasy/seasonal_projections/GUIDE.md)
- [Publication system](publishing/README.md)

## License

This repository uses the [PolyForm Noncommercial License 1.0.0](LICENSE). You may read, modify, and use the code for noncommercial work. Commercial use requires a separate license.

Copyright © 2026 Joseph Schoenbaum.
