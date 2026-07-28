"""Batch-3c proof for the extracted Weekly Fantasy + League History pages. Each renders
offline-clean and owns its own controls (filter independence); League History lands on an
EMPTY league-ID box with the resting prompt (the earlier fix survives extraction).
Hermetic (APP_OFFLINE=1).
"""
import os
import sys
from pathlib import Path

import pandas as pd

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import page_league_history


def _render_page(tmp_path, module):
    h = tmp_path / f"h_{module}.py"
    h.write_text(f"import sys; sys.path.insert(0, r'{_HERE}')\n"
                 f"import {module} as p\np.render()\n", encoding="utf-8")
    at = AppTest.from_file(str(h), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _control_keys(at):
    return {getattr(w, "key", None) for w in list(at.selectbox) + list(at.slider)}


def test_weekly_fantasy_renders_and_owns_controls(tmp_path):
    at = _render_page(tmp_path, "page_weekly_fantasy")
    keys = _control_keys(at)
    assert {"wf_season", "wf_week"} <= keys, f"Weekly Fantasy must own Season+Week; got {keys}"
    assert not any(str(k).startswith(("wp_", "tr_")) for k in keys), \
        "Weekly Fantasy must not carry another page's controls"


def test_weekly_actuals_cache_one_season_across_week_filters(monkeypatch):
    """Week changes reuse a bounded cached season pull without changing its API."""
    import nflreadpy as nfl
    import page_weekly_fantasy as weekly

    calls = []
    raw = pd.DataFrame([
        {
            "season_type": "REG", "week": 1, "position": "QB", "player_id": "qb1",
            "passing_yards": 250, "passing_tds": 2, "passing_interceptions": 0,
            "rushing_yards": 0, "rushing_tds": 0, "receptions": 0,
            "receiving_yards": 0, "receiving_tds": 0,
            "rushing_fumbles_lost": 0, "receiving_fumbles_lost": 0,
        },
        {
            "season_type": "REG", "week": 2, "position": "WR", "player_id": "wr1",
            "passing_yards": 0, "passing_tds": 0, "passing_interceptions": 0,
            "rushing_yards": 0, "rushing_tds": 0, "receptions": 5,
            "receiving_yards": 100, "receiving_tds": 1,
            "rushing_fumbles_lost": 0, "receiving_fumbles_lost": 0,
        },
    ])

    def _load_player_stats(seasons):
        calls.append(tuple(seasons))
        return raw.copy()

    monkeypatch.setattr(weekly, "_OFFLINE", False)
    monkeypatch.setattr(nfl, "load_player_stats", _load_player_stats)
    weekly._load_actual_stats_season.clear()
    try:
        week_one = weekly.load_actual_stats(2025, 1)
        week_two = weekly.load_actual_stats(2025, 2)

        assert calls == [(2025,)]
        assert set(week_one) == {
            "half_ppr", "qb_pass_yds", "qb_rush_yds", "rb_rush_yds", "rb_rec_yds",
            "wr_rec_yds", "wr_recs", "te_rec_yds", "te_recs",
        }
        assert week_one["half_ppr"] == {"qb1": 18.0}
        assert week_one["qb_pass_yds"] == {"qb1": 250}
        assert week_two["half_ppr"] == {"wr1": 18.5}
        assert week_two["wr_rec_yds"] == {"wr1": 100}
        assert week_two["wr_recs"] == {"wr1": 5}

        weekly._load_actual_stats_season.clear()
        missing_column = raw.drop(columns=["receiving_tds"])
        monkeypatch.setattr(nfl, "load_player_stats", lambda seasons: missing_column.copy())
        assert weekly.load_actual_stats(2024, 1) == {}

        monkeypatch.setattr(weekly, "_OFFLINE", True)
        assert weekly.load_actual_stats(2025, 3) == {}
        assert calls == [(2025,)]
    finally:
        weekly._load_actual_stats_season.clear()


def test_league_history_renders_and_lands_empty(tmp_path):
    at = _render_page(tmp_path, "page_league_history")
    ti = [t for t in at.text_input if getattr(t, "key", None) == "lh_league_id"]
    assert ti, "League History must render its league-ID input"
    assert ti[0].value == "", "League History must land on an EMPTY league-ID box"
    assert any(b.label == "Load league history" for b in at.button), \
        "League History must require an explicit Load action"
    info = " ".join(str(i.value) for i in at.info)
    assert "Enter your Sleeper league ID" in info, "resting-state prompt must be shown"


def test_league_history_rejects_implausible_ids_before_fetch():
    assert page_league_history._league_id_error("1255197436951932928") is None
    assert "digits only" in page_league_history._league_id_error("abc123")
    assert "does not look like" in page_league_history._league_id_error("123")


def test_rookie_board_excludes_direct_pff_fields_and_explains_availability(tmp_path):
    """The public Rookie Board excludes direct PFF data and explains blank projections."""
    at = _render_page(tmp_path, "page_rookie_board")
    assert any(w.label == "Draft class" for w in at.selectbox)
    assert any(w.label == "Position" for w in at.selectbox)
    # Three tables since 2026-07-27: the rookie board itself, plus the collapsed
    # "college QBs/RBs/WRs/TEs not in this rookie class" views. ALL must stay free of direct PFF fields.
    assert len(at.dataframe) == 5

    banned_pff = {"PFF Grade", "PFF Grade (Percentile)", "PFF Efficiency",
                  "PFF Efficiency (Percentile)", "grades_pass", "btt_rate", "twp_rate",
                  "pressure_grade", "accuracy_pct", "grades_run"}
    tables = []
    for element in at.dataframe:
        value = element.value
        tables.append(value.data if hasattr(value, "data") else value)
    for table in tables:
        assert not banned_pff & set(table.columns),             f"direct PFF fields leaked into a public table: {banned_pff & set(table.columns)}"

    shown = tables[0]
    assert {"Draft-Capital Hit-%", "College Hit-%", "Full Hit-%", "College Talent",
            "Athleticism (Percentile)", "Production (Percentile)"} <= set(shown.columns)

    for watch in tables[1:]:
        assert {"Player", "College", "College Talent"} <= set(watch.columns)

    copy = " ".join(str(x.value) for x in at.caption)
    assert "top-24 for RB/WR or top-12 for QB/TE" in copy
    assert "RB/WR/TE" in copy
    assert "Sleeper has not published one" in copy
    assert "Rookie QB model projections are intentionally withheld" in copy


def test_rookie_board_csvs_exclude_direct_pff_columns():
    banned = {"pff_grade", "pff_eff", "pct_pff_grade", "pct_pff_eff"}
    board_dir = _HERE / "fantasy" / "rookie" / "board_data"
    for cls in (2024, 2025, 2026):
        columns = set(pd.read_csv(board_dir / f"rookie_board_{cls}.csv", nrows=0).columns)
        assert not columns & banned


def test_league_history_caps_matchup_workers_without_network(monkeypatch):
    """A submitted history may fetch many weeks, but never unbounded concurrency."""
    seen_workers = []

    class _Executor:
        def __init__(self, max_workers):
            seen_workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def map(self, fn, values):
            return map(fn, values)

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    league_id = "1255197436951932928"

    def _sleeper_get(url):
        if url.endswith(f"/league/{league_id}"):
            return {
                "name": "Test league", "season": "2025", "status": "complete",
                "settings": {"playoff_week_start": 15}, "previous_league_id": "0",
            }
        return []

    monkeypatch.setattr(page_league_history, "_sleeper_get", _sleeper_get)
    monkeypatch.setattr(page_league_history._cf, "ThreadPoolExecutor", _Executor)
    monkeypatch.setattr(page_league_history.req, "get", lambda *_args, **_kwargs: _Response())
    page_league_history._fetch_sleeper_history.clear()
    try:
        history = page_league_history._fetch_sleeper_history(league_id)
        assert history["seasons"]
        assert seen_workers == [page_league_history._MATCHUP_FETCH_WORKERS]
        assert seen_workers[0] <= 6
    finally:
        page_league_history._fetch_sleeper_history.clear()


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        test_weekly_fantasy_renders_and_owns_controls(p)
        test_league_history_renders_and_lands_empty(p)
    print("OK  WF owns wf_* controls; LH lands empty with the resting prompt")
