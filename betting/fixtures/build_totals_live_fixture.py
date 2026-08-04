"""Regenerate the retained REAL-schedule fixture used by `betting/test_totals_live.py`.

The fixture is a genuine nflverse schedule slice (no synthesised games, no edited values)
restricted to thirteen franchises across five seasons, chosen so that the retained rows contain
the shapes that broke the live totals path:

* **team aliases / relocations** — SD (2016) → LAC (2017+), OAK (2016–19) → LV (2020+);
  LA appears from 2016 (the STL relocation is already collapsed upstream by nflverse).
* **byes** — every team's week sequence has real gaps.
* **missing weather** — ~49 % of the retained rows have a null `temp`/`wind` in the source,
  and the derived weather CSV keeps only the non-null ones, so a lookup miss is the norm.
* **first game of a season** — 2016 week 1 rows have no prior history inside the fixture,
  so the "no prior game" branch is exercised on real rows.
* **postponed / out-of-order dates** — the 2020 COVID reschedules are retained as real rows:
  2020_05_BUF_TEN (Tuesday), 2020_12_BAL_PIT (Wednesday), 2020_13_DAL_BAL (Tuesday).
  PIT/TEN/BAL are in the team set specifically to carry them.
* **playoffs** — WC/DIV/CON/SB rows are kept, so week numbers run past 18.

`2021 week 18` is the designated FUTURE slate: the test blanks its scores to simulate a
week that has not kicked off. Its eight games carry four distinct real roof strings
(dome / open / closed), which is what makes the `is_dome` assertion meaningful.

Play-by-play is NOT retained (it would dwarf the repo); the test synthesises a deterministic
play table from these real game ids. That is a documented limitation of the pace column only.

Run:  python betting/fixtures/build_totals_live_fixture.py
"""
from pathlib import Path

import nflreadpy as nfl

SEASONS = [2016, 2017, 2019, 2020, 2021]
TEAMS = {"SD", "LAC", "OAK", "LV", "LA", "ARI", "NO", "DET", "ATL", "MIN",
         "PIT", "TEN", "BAL"}
COLS = ["game_id", "season", "game_type", "week", "gameday", "home_team", "away_team",
        "home_score", "away_score", "roof", "surface", "div_game", "spread_line",
        "total_line", "temp", "wind", "result"]
OUT = Path(__file__).resolve().parent


def main():
    s = nfl.load_schedules(SEASONS).to_pandas()
    f = s[s["home_team"].isin(TEAMS) | s["away_team"].isin(TEAMS)][COLS].copy()
    f = f.sort_values(["season", "week", "game_id"]).reset_index(drop=True)
    f.to_csv(OUT / "totals_live_schedule.csv", index=False)

    # The weather file is a RETAINED OBSERVED record, so rows for the designated future
    # slate are excluded: a game that has not kicked off has no observed weather, and
    # leaving 2021 week 18 in would let post-game information into a "future" simulation.
    future = (f["season"] == 2021) & (f["week"] == 18)
    keep = f["temp"].notna() & f["wind"].notna() & ~future
    wx = f.loc[keep, ["game_id", "temp", "wind"]].copy()
    wx = wx.rename(columns={"temp": "temp_f", "wind": "wind_mph"})
    wx.to_csv(OUT / "totals_live_weather.csv", index=False)
    print(f"schedule rows={len(f)}  weather rows={len(wx)}")


if __name__ == "__main__":
    main()
