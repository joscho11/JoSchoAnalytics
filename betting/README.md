# Betting display

This folder is website display data and rules. Training lives in `spread_v3_prod`.

| Path | Role |
|---|---|
| `anytime_td/` | Published 2026 Anytime TD boards and 2025 demo CSVs (Weeks 10-17). Active release and grading state: `data/releases/manifest.json`. Guide: [anytime_td/GUIDE.md](anytime_td/GUIDE.md) |
| `live_2026.py` | 2026 HIGH / PASS rules |
| `calibration.py` | Cover rates from the graded tracker |
| `predictions_tracker.csv` | Graded 2025 demo plus stamped 2026 rows |
| `totals_tracker.csv` | 2025 experimental totals tracking |
| `slate_2026.csv` | 2026 matchup skeleton |
| `nfl_2026_schedule.csv` | Schedule used by the week page |

See [GUIDE.md](GUIDE.md) for claims and limits.

Use `python -m publishing.cli status` to inspect the active prediction and
fantasy releases. TD releases are recorded in the same manifest.
