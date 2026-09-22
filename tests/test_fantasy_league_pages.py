"""Batch-3c proof for the extracted Weekly Fantasy + League History pages. Each renders
offline-clean and owns its own controls (filter independence); League History lands on an
EMPTY league-ID box with the resting prompt (the earlier fix survives extraction).
Hermetic (APP_OFFLINE=1).
"""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_SITE_PAGES))

import page_league_history
import page_common
import espn_league_history
import yahoo_league_history
import cbs_league_history
from fantasy import league_intelligence as league_intel


def _render_page(tmp_path, module):
    h = tmp_path / f"h_{module}.py"
    h.write_text(f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
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
    import page_common
    default_season, default_week = page_common.release_default_selection("fantasy", (2025, 10))
    controls = {w.key: w.value for w in at.selectbox}
    assert controls["wf_season"] == 2026 == default_season
    # The page follows the newest published week; pinning a number here breaks
    # every time a new week ships.
    assert int(controls["wf_week"]) == int(default_week)
    assert not any(str(k).startswith(("wp_", "tr_")) for k in keys), \
        "Weekly Fantasy must not carry another page's controls"


def test_weekly_actuals_cache_one_season_across_week_filters(monkeypatch):
    """Week changes reuse a bounded cached season pull without changing its API."""
    import nflreadpy as nfl
    import page_weekly_fantasy as weekly

    calls = []
    schedule_calls = []
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

    def _load_schedules(seasons):
        schedule_calls.append(tuple(seasons))
        season = int(seasons[0])
        return pd.DataFrame({
            "season": [season, season],
            "season_type": ["REG", "REG"],
            "week": [1, 2],
            "home_score": [24, 21],
            "away_score": [20, 17],
        })

    monkeypatch.setattr(weekly, "_OFFLINE", False)
    monkeypatch.setattr(nfl, "load_player_stats", _load_player_stats)
    monkeypatch.setattr(nfl, "load_schedules", _load_schedules)
    weekly._load_actual_stats_season.clear()
    weekly._load_schedule_season.clear()
    try:
        week_one = weekly.load_actual_stats(2025, 1)
        week_two = weekly.load_actual_stats(2025, 2)

        assert calls == [(2025,)]
        assert schedule_calls == [(2025,)]
        assert set(week_one) == {
            "half_ppr", "qb_pass_yds", "qb_rush_yds", "rb_rush_yds", "rb_rec_yds",
            "wr_rec_yds", "wr_recs", "te_rec_yds", "te_recs", "qb_recs", "rb_recs",
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
        weekly._load_schedule_season.clear()


def test_league_history_renders_and_lands_empty(tmp_path):
    at = _render_page(tmp_path, "page_league_history")
    ti = [t for t in at.text_input if getattr(t, "key", None) == "lh_league_id"]
    assert ti, "League History must render its league-ID input"
    assert ti[0].value == "", "League History must land on an EMPTY league-ID box"
    assert any(b.label == "Load league history" for b in at.button), \
        "League History must require an explicit Load action"
    depth = next(w for w in at.segmented_control if w.key == "lh_history_depth")
    assert depth.value == "Recent 3 seasons"
    info = " ".join(str(i.value) for i in at.info)
    assert "Enter your Sleeper league ID" in info, "resting-state prompt must be shown"
    assert "Recent 3 seasons" in info
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "Copy League ID" in markdown
    assert "at the end of the page URL" in markdown
    assert any(
        expander.label == "Where to find your league details" for expander in at.expander
    )


def test_league_history_exposes_espn_provider_and_season(tmp_path):
    at = _render_page(tmp_path, "page_league_history")
    provider = next(w for w in at.segmented_control if w.key == "lh_provider")
    provider.set_value("ESPN")
    at = at.run()
    assert not at.exception, at.exception
    assert next(w for w in at.number_input if w.key == "lh_espn_season")
    league_input = next(w for w in at.text_input if w.key == "lh_league_id")
    assert league_input.label == "ESPN League ID"
    info = " ".join(str(item.value) for item in at.info)
    assert "public ESPN league ID" in info
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "League Info" in markdown
    assert "viewable to public" in markdown
    assert "ESPN keeps membership invite-only" in markdown
    access = next(w for w in at.segmented_control if w.key == "lh_espn_access")
    assert access.value == "Public"
    access.set_value("Private")
    at = at.run()
    private_inputs = {
        widget.key: widget
        for widget in at.text_input
        if widget.key in {"lh_espn_swid", "lh_espn_s2"}
    }
    assert set(private_inputs) == {"lh_espn_swid", "lh_espn_s2"}
    assert all(widget.value == "" for widget in private_inputs.values())
    captions = " ".join(str(item.value) for item in at.caption)
    assert "Do not paste them into chat" in captions
    assert "never logs or shared-caches them" in captions
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "normal iPhone and Android browser menus do not expose" in markdown
    assert "Application → Storage → Cookies" in markdown
    assert "Developer Tools → Storage → Cookies" in markdown
    assert "clears both fields after a successful load" in markdown


def test_private_espn_history_stays_in_session_and_clears_cookie_fields(tmp_path):
    fixture = {
        "league_name": "Private Test League",
        "provider": "ESPN",
        "player_directory": {},
        "seasons": {"2025": {
            "league_id": "1460131",
            "draft_id": "",
            "status": "complete",
            "champion": {"username": "Alice", "team_name": "A Team"},
            "runner_up": {"username": "Bob", "team_name": "B Team"},
            "toilet_champion": {"username": "Bob", "team_name": "B Team"},
            "toilet_champions": [{"username": "Bob", "team_name": "B Team"}],
            "toilet_finalists": ["Alice", "Bob"],
            "toilet_bracket": ["Alice", "Bob"],
            "standings": [
                {
                    "roster_id": 1, "owner_id": "owner-a", "username": "Alice",
                    "team_name": "A Team", "wins": 1, "losses": 0,
                    "fpts": 110.0, "fpts_against": 90.0, "playoff_finish": 1,
                },
                {
                    "roster_id": 2, "owner_id": "owner-b", "username": "Bob",
                    "team_name": "B Team", "wins": 0, "losses": 1,
                    "fpts": 90.0, "fpts_against": 110.0, "playoff_finish": 2,
                },
            ],
            "matchups": [{
                "season": "2025", "week": 1, "is_playoff": False,
                "rid_a": "1", "score_a": 110.0,
                "rid_b": "2", "score_b": 90.0,
            }],
            "draft_picks": [],
            "roster_entries": [],
            "league_settings": {
                "total_rosters": 2, "roster_positions": [],
                "scoring_settings": {}, "waiver_type": 0, "waiver_budget": None,
            },
        }},
    }
    harness = tmp_path / "private_espn_loaded.py"
    harness.write_text(
        f"import sys\nsys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import page_league_history as p\n"
        "p._OFFLINE = False\n"
        f"_fixture = {fixture!r}\n"
        "def _load(league_id, season, max_seasons=None, private_credentials=None):\n"
        "    assert league_id == '1460131'\n"
        "    assert private_credentials == ('synthetic-s2', '{synthetic-swid}')\n"
        "    return _fixture, None\n"
        "p._load_espn_history_with_status = _load\n"
        "p.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    next(w for w in at.segmented_control if w.key == "lh_provider").set_value("ESPN")
    at = at.run()
    next(w for w in at.segmented_control if w.key == "lh_espn_access").set_value("Private")
    at = at.run()
    next(w for w in at.text_input if w.key == "lh_league_id").set_value("1460131")
    next(w for w in at.number_input if w.key == "lh_espn_season").set_value(2025)
    next(w for w in at.text_input if w.key == "lh_espn_s2").set_value("synthetic-s2")
    next(w for w in at.text_input if w.key == "lh_espn_swid").set_value("{synthetic-swid}")
    next(b for b in at.button if b.label == "Load league history").click()
    at = at.run()

    assert not at.exception, at.exception
    assert any(header.value == "Private Test League" for header in at.header)
    assert next(w for w in at.text_input if w.key == "lh_espn_s2").value == ""
    assert next(w for w in at.text_input if w.key == "lh_espn_swid").value == ""
    assert any(
        "Stored only in this browser session" in str(caption.value)
        for caption in at.caption
    )


def test_league_history_rejects_implausible_ids_before_fetch():
    assert page_league_history._league_id_error("1255197436951932928") is None
    assert "digits only" in page_league_history._league_id_error("abc123")
    assert "does not look like" in page_league_history._league_id_error("123")


def test_league_history_validates_espn_id_and_season():
    assert page_league_history._league_request_error("ESPN", "48153503", 2025) is None
    assert "digits only" in page_league_history._league_request_error("ESPN", "abc", 2025)
    assert "currently supports" in page_league_history._league_request_error(
        "ESPN", "48153503", 2017,
    )
    assert "both the SWID and espn_s2" in page_league_history._league_request_error(
        "ESPN", "48153503", 2025, "Private", "", "",
    )
    assert page_league_history._league_request_error(
        "ESPN", "48153503", 2025, "Private", "s2-value", "{swid-value}",
    ) is None


def test_private_espn_requests_are_credentialed_and_never_shared_cached(monkeypatch):
    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"seasonId": 2025, "settings": {"name": "Private Test"}}

    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setattr(espn_league_history.requests, "get", fake_get)
    for _ in range(2):
        payload = espn_league_history._espn_get_private(
            "1460131",
            2025,
            ("mSettings",),
            "espn_s2=session-cookie-value",
            "SWID={synthetic-swid}",
        )
        assert payload["settings"]["name"] == "Private Test"

    assert len(calls) == 2, "credentialed requests must bypass shared st.cache_data"
    assert calls[0]["cookies"] == {
        "espn_s2": "session-cookie-value",
        "SWID": "{synthetic-swid}",
    }
    assert not hasattr(espn_league_history._espn_get_private, "clear")


def test_private_espn_401_does_not_echo_cookie_values(monkeypatch):
    class Response:
        status_code = 401

    monkeypatch.setattr(
        espn_league_history.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )
    with pytest.raises(espn_league_history.EspnLeagueError) as caught:
        espn_league_history._espn_get_private(
            "1460131", 2025, ("mSettings",), "sensitive-s2-value", "{sensitive-swid}",
        )
    message = str(caught.value)
    assert "Recopy the SWID and espn_s2" in message
    assert "sensitive-s2-value" not in message
    assert "sensitive-swid" not in message


def test_espn_season_normalizes_to_existing_history_schema():
    data = {
        "members": [
            {"id": "owner-a", "displayName": "Alice"},
            {"id": "owner-b", "displayName": "Bob"},
        ],
        "status": {
            "firstScoringPeriod": 1,
            "finalScoringPeriod": 2,
            "latestScoringPeriod": 2,
        },
        "settings": {
            "scheduleSettings": {"matchupPeriodCount": 1},
            "rosterSettings": {"lineupSlotCounts": {"0": 1, "2": 1, "20": 3}},
            "scoringSettings": {"scoringItems": [
                {"statId": 4, "points": 4},
                {"statId": 53, "points": 0.5},
            ]},
            "acquisitionSettings": {
                "isUsingAcquisitionBudget": True,
                "acquisitionBudget": 100,
            },
        },
        "teams": [
            {
                "id": 1, "name": "A Team", "primaryOwner": "owner-a",
                "rankCalculatedFinal": 1,
                "record": {"overall": {
                    "wins": 1, "losses": 0, "pointsFor": 110,
                    "pointsAgainst": 90,
                }},
            },
            {
                "id": 2, "name": "B Team", "primaryOwner": "owner-b",
                "rankCalculatedFinal": 2,
                "record": {"overall": {
                    "wins": 0, "losses": 1, "pointsFor": 90,
                    "pointsAgainst": 110,
                }},
            },
        ],
        "schedule": [{
            "id": 10, "matchupPeriodId": 1,
            "home": {"teamId": 1, "pointsByScoringPeriod": {"1": 110}},
            "away": {"teamId": 2, "pointsByScoringPeriod": {"1": 90}},
        }],
        "draftDetail": {"picks": [
            {
                "teamId": 1, "playerId": 101, "overallPickNumber": 1,
                "roundId": 1, "roundPickNumber": 1,
            },
            {
                "teamId": 2, "playerId": 202, "overallPickNumber": 2,
                "roundId": 1, "roundPickNumber": 2,
            },
            {
                "teamId": 1, "playerId": 303, "overallPickNumber": 3,
                "roundId": 2, "roundPickNumber": 1,
            },
        ]},
    }
    weekly = {1: {"teams": [
        {"id": 1, "roster": {"entries": [{
            "playerId": 101, "lineupSlotId": 2,
            "playerPoolEntry": {"player": {
                "id": 101, "fullName": "Runner One", "firstName": "Runner",
                "lastName": "One", "eligibleSlots": [2, 20],
                "stats": [{
                    "scoringPeriodId": 1, "statSourceId": 0, "appliedTotal": 22.5,
                }],
            }},
        }]}},
        {"id": 2, "roster": {"entries": [{
            "playerId": 202, "lineupSlotId": 0,
            "playerPoolEntry": {"player": {
                "id": 202, "fullName": "Passer Two", "firstName": "Passer",
                "lastName": "Two", "eligibleSlots": [0, 7, 20],
                "stats": [{
                    "scoringPeriodId": 1, "statSourceId": 0, "appliedTotal": 18,
                }],
            }},
        }]}},
    ]}}

    payload, players = espn_league_history.normalize_season(
        "48153503", 2025, data, weekly,
        [{
            "id": 303, "fullName": "Cut Before Week One", "firstName": "Cut",
            "lastName": "Before Week One", "eligibleSlots": [4, 20],
        }],
    )

    assert payload["champion"]["username"] == "Alice"
    assert payload["runner_up"]["username"] == "Bob"
    assert payload["matchups"] == [{
        "season": "2025", "week": 1, "is_playoff": False,
        "rid_a": "1", "score_a": 110.0,
        "rid_b": "2", "score_b": 90.0,
    }]
    assert payload["roster_entries"][0]["players_points"]["101"] == 22.5
    assert payload["draft_picks"][0]["metadata"]["position"] == "RB"
    assert payload["draft_picks"][2]["metadata"]["full_name"] == "Cut Before Week One"
    assert payload["league_settings"]["scoring_settings"] == {
        "rec": 0.5, "pass_td": 4.0,
    }
    assert payload["league_settings"]["waiver_type"] == 2
    assert players["202"]["position"] == "QB"


def test_league_history_exposes_yahoo_provider_and_season(tmp_path):
    at = _render_page(tmp_path, "page_league_history")
    provider = next(w for w in at.segmented_control if w.key == "lh_provider")
    provider.set_value("Yahoo")
    at = at.run()
    assert not at.exception, at.exception
    assert next(w for w in at.number_input if w.key == "lh_yahoo_season")
    league_input = next(w for w in at.text_input if w.key == "lh_league_id")
    assert league_input.label == "Yahoo League ID"
    info = " ".join(str(item.value) for item in at.info)
    assert "public Yahoo league ID" in info
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "/f1/" in markdown
    assert "publicly viewable" in markdown
    access = next(w for w in at.segmented_control if w.key == "lh_yahoo_access")
    assert access.value == "Public"
    access.set_value("Private")
    at = at.run()
    private_inputs = {
        widget.key: widget
        for widget in at.text_input
        if widget.key in {"lh_yahoo_y", "lh_yahoo_t"}
    }
    assert set(private_inputs) == {"lh_yahoo_y", "lh_yahoo_t"}
    assert all(widget.value == "" for widget in private_inputs.values())
    captions = " ".join(str(item.value) for item in at.caption)
    assert "Do not paste them into chat" in captions
    assert "never logs or shared-caches them" in captions
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert "normal iPhone and Android browser menus do not expose" in markdown
    assert "Application → Storage → Cookies" in markdown
    assert "Developer Tools → Storage → Cookies" in markdown
    assert "clears both fields after a successful load" in markdown


def test_private_yahoo_history_stays_in_session_and_clears_cookie_fields(tmp_path):
    fixture = {
        "league_name": "Private Yahoo League",
        "provider": "Yahoo",
        "player_directory": {},
        "seasons": {"2025": {
            "league_id": "123456",
            "draft_id": "",
            "status": "complete",
            "champion": {"username": "Alice", "team_name": "A Team"},
            "runner_up": {"username": "Bob", "team_name": "B Team"},
            "toilet_champion": {"username": "Bob", "team_name": "B Team"},
            "toilet_champions": [{"username": "Bob", "team_name": "B Team"}],
            "toilet_finalists": ["Alice", "Bob"],
            "toilet_bracket": ["Alice", "Bob"],
            "standings": [
                {
                    "roster_id": 1, "owner_id": "owner-a", "username": "Alice",
                    "team_name": "A Team", "wins": 1, "losses": 0,
                    "fpts": 110.0, "fpts_against": 90.0, "playoff_finish": 1,
                },
                {
                    "roster_id": 2, "owner_id": "owner-b", "username": "Bob",
                    "team_name": "B Team", "wins": 0, "losses": 1,
                    "fpts": 90.0, "fpts_against": 110.0, "playoff_finish": 2,
                },
            ],
            "matchups": [{
                "season": "2025", "week": 1, "is_playoff": False,
                "rid_a": "1", "score_a": 110.0,
                "rid_b": "2", "score_b": 90.0,
            }],
            "draft_picks": [],
            "roster_entries": [],
            "league_settings": {
                "total_rosters": 2, "roster_positions": [],
                "scoring_settings": {}, "waiver_type": 0, "waiver_budget": None,
            },
        }},
    }
    harness = tmp_path / "private_yahoo_loaded.py"
    harness.write_text(
        f"import sys\nsys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import page_league_history as p\n"
        "p._OFFLINE = False\n"
        f"_fixture = {fixture!r}\n"
        "def _load(league_id, season, max_seasons=None, private_credentials=None, game_key=None):\n"
        "    assert league_id == '123456'\n"
        "    assert private_credentials == ('yahoo-y-value', 'yahoo-t-value')\n"
        "    return _fixture, None\n"
        "p._load_yahoo_history_with_status = _load\n"
        "p.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    next(w for w in at.segmented_control if w.key == "lh_provider").set_value("Yahoo")
    at = at.run()
    next(w for w in at.segmented_control if w.key == "lh_yahoo_access").set_value("Private")
    at = at.run()
    next(w for w in at.text_input if w.key == "lh_league_id").set_value("123456")
    next(w for w in at.number_input if w.key == "lh_yahoo_season").set_value(2025)
    next(w for w in at.text_input if w.key == "lh_yahoo_y").set_value("yahoo-y-value")
    next(w for w in at.text_input if w.key == "lh_yahoo_t").set_value("yahoo-t-value")
    next(b for b in at.button if b.label == "Load league history").click()
    at = at.run()

    assert not at.exception, at.exception
    assert any(header.value == "Private Yahoo League" for header in at.header)
    assert next(w for w in at.text_input if w.key == "lh_yahoo_y").value == ""
    assert next(w for w in at.text_input if w.key == "lh_yahoo_t").value == ""
    assert any(
        "Stored only in this browser session" in str(caption.value)
        for caption in at.caption
    )


def test_league_history_validates_yahoo_id_and_season():
    assert page_league_history._league_request_error("Yahoo", "123456", yahoo_season=2025) is None
    assert "digits only" in page_league_history._league_request_error("Yahoo", "abc", yahoo_season=2025)
    assert "currently supports" in page_league_history._league_request_error(
        "Yahoo", "123456", yahoo_season=2017,
    )
    assert "both the Y and T" in page_league_history._league_request_error(
        "Yahoo", "123456", yahoo_season=2025, yahoo_access="Private", yahoo_y="", yahoo_t="",
    )
    assert page_league_history._league_request_error(
        "Yahoo", "123456", yahoo_season=2025, yahoo_access="Private",
        yahoo_y="y-value", yahoo_t="t-value",
    ) is None
    parsed_id, game_key, season = yahoo_league_history.parse_league_ref(
        "https://football.fantasysports.yahoo.com/2025/f1/123456"
    )
    assert parsed_id == "123456"
    assert season == 2025
    parsed_id, game_key, season = yahoo_league_history.parse_league_ref("461.l.123456")
    assert parsed_id == "123456"
    assert game_key == "461"
    assert season == 2025


def test_private_yahoo_requests_are_credentialed_and_never_shared_cached(monkeypatch):
    calls = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"fantasy_content": {"league": [
                {"league_id": "123456", "season": "2025", "name": "Private Yahoo",
                 "league_key": "461.l.123456", "renew": ""},
            ]}}

    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setattr(yahoo_league_history.requests, "get", fake_get)
    for _ in range(2):
        payload = yahoo_league_history._yahoo_get_private(
            "https://example.invalid/league",
            "Y=session-y",
            "T=session-t",
        )
        assert payload["fantasy_content"]["league"][0]["name"] == "Private Yahoo"

    assert len(calls) == 2, "credentialed requests must bypass shared st.cache_data"
    assert calls[0]["cookies"] == {"Y": "session-y", "T": "session-t"}
    assert not hasattr(yahoo_league_history._yahoo_get_private, "clear")


def test_private_yahoo_401_does_not_echo_cookie_values(monkeypatch):
    class Response:
        status_code = 401

    monkeypatch.setattr(
        yahoo_league_history.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )
    with pytest.raises(yahoo_league_history.YahooLeagueError) as caught:
        yahoo_league_history._yahoo_get_private(
            "https://example.invalid/league", "sensitive-y-value", "sensitive-t-value",
        )
    message = str(caught.value)
    assert "Recopy the Y and T" in message
    assert "sensitive-y-value" not in message
    assert "sensitive-t-value" not in message


def test_yahoo_season_normalizes_to_existing_history_schema():
    meta = {
        "league_id": "123456",
        "season": "2025",
        "name": "Test Yahoo",
        "num_teams": 2,
        "start_week": "1",
        "end_week": "1",
        "current_week": "1",
        "is_finished": 1,
        "league_key": "461.l.123456",
    }
    extras = {
        "settings": [{
            "uses_faab": "1",
            "roster_positions": [
                {"roster_position": {"position": "QB", "count": 1, "is_starting_position": 1}},
                {"roster_position": {"position": "BN", "count": 3, "is_starting_position": 0}},
            ],
            "stat_categories": {"stats": [
                {"stat": {"stat_id": 11, "name": "Receptions"}},
                {"stat": {"stat_id": 5, "name": "Passing Touchdowns"}},
            ]},
            "stat_modifiers": {"stats": [
                {"stat": {"stat_id": 11, "value": "0.5"}},
                {"stat": {"stat_id": 5, "value": "4"}},
            ]},
        }],
        "standings": [{
            "teams": {
                "0": {"team": [
                    [
                        {"team_key": "461.l.123456.t.1"},
                        {"team_id": "1"},
                        {"name": "A Team"},
                        {"draft_position": 1},
                        {"managers": [{"manager": {
                            "manager_id": "1", "nickname": "Alice", "guid": "guid-a",
                        }}]},
                    ],
                    {"team_standings": {
                        "rank": "1",
                        "outcome_totals": {"wins": 1, "losses": 0, "ties": 0},
                        "points_for": "110",
                        "points_against": "90",
                    }},
                ]},
                "1": {"team": [
                    [
                        {"team_key": "461.l.123456.t.2"},
                        {"team_id": "2"},
                        {"name": "B Team"},
                        {"draft_position": 2},
                        {"managers": [{"manager": {
                            "manager_id": "2", "nickname": "Bob", "guid": "guid-b",
                        }}]},
                    ],
                    {"team_standings": {
                        "rank": "2",
                        "outcome_totals": {"wins": 0, "losses": 1, "ties": 0},
                        "points_for": "90",
                        "points_against": "110",
                    }},
                ]},
                "count": 2,
            },
        }],
        "draft_results": {
            "0": {"draft_result": {
                "pick": 1, "round": 1,
                "team_key": "461.l.123456.t.1", "player_key": "461.p.101",
            }},
            "1": {"draft_result": {
                "pick": 2, "round": 1,
                "team_key": "461.l.123456.t.2", "player_key": "461.p.202",
            }},
            "count": 2,
        },
    }
    scoreboards = {1: {
        "week": "1",
        "0": {"matchups": {
            "0": {"matchup": {
                "week": "1",
                "is_playoffs": "0",
                "0": {"teams": {
                    "0": {"team": [
                        [{"team_key": "461.l.123456.t.1"}, {"team_id": "1"}],
                        {"team_points": {"total": "110"}},
                    ]},
                    "1": {"team": [
                        [{"team_key": "461.l.123456.t.2"}, {"team_id": "2"}],
                        {"team_points": {"total": "90"}},
                    ]},
                    "count": 2,
                }},
            }},
            "count": 1,
        }},
    }}
    weekly = {1: {
        "0": {"team": [
            [{"team_key": "461.l.123456.t.1"}, {"team_id": "1"}],
            {"roster": {"0": {"players": {
                "0": {"player": [
                    [
                        {"player_key": "461.p.101"},
                        {"player_id": "101"},
                        {"name": {"full": "Runner One", "first": "Runner", "last": "One"}},
                        {"primary_position": "RB"},
                    ],
                    {"selected_position": {"position": "RB"}},
                    {"player_points": {"total": "22.5"}},
                ]},
                "count": 1,
            }}}},
        ]},
        "1": {"team": [
            [{"team_key": "461.l.123456.t.2"}, {"team_id": "2"}],
            {"roster": {"0": {"players": {
                "0": {"player": [
                    [
                        {"player_key": "461.p.202"},
                        {"player_id": "202"},
                        {"name": {"full": "Passer Two", "first": "Passer", "last": "Two"}},
                        {"primary_position": "QB"},
                    ],
                    {"selected_position": {"position": "BN"}},
                    {"player_points": {"total": "18"}},
                ]},
                "count": 1,
            }}}},
        ]},
        "count": 2,
    }}
    payload, players = yahoo_league_history.normalize_season(
        "123456", 2025, meta, extras, scoreboards, weekly,
    )
    assert payload["champion"]["username"] == "Alice"
    assert payload["runner_up"]["username"] == "Bob"
    assert payload["matchups"] == [{
        "season": "2025", "week": 1, "is_playoff": False,
        "rid_a": "1", "score_a": 110.0,
        "rid_b": "2", "score_b": 90.0,
    }]
    assert payload["roster_entries"][0]["players_points"]["101"] == 22.5
    assert payload["roster_entries"][0]["starters"] == ["101"]
    assert payload["roster_entries"][1]["starters"] == []
    assert payload["draft_picks"][0]["metadata"]["position"] == "RB"
    assert payload["league_settings"]["scoring_settings"] == {
        "rec": 0.5, "pass_td": 4.0,
    }
    assert payload["league_settings"]["waiver_type"] == 2
    assert players["202"]["position"] == "QB"


def test_league_history_exposes_cbs_provider_and_season(tmp_path):
    assert page_league_history._LEAGUE_PROVIDERS == ("Sleeper", "ESPN", "Yahoo", "CBS")
    at = _render_page(tmp_path, "page_league_history")
    provider = next(w for w in at.segmented_control if w.key == "lh_provider")
    provider.set_value("CBS")
    at = at.run()
    assert not at.exception, at.exception
    assert next(w for w in at.number_input if w.key == "lh_cbs_season")
    league_input = next(w for w in at.text_input if w.key == "lh_league_id")
    assert league_input.label == "CBS League ID"
    info = " ".join(str(item.value) for item in at.info)
    assert "CBS league ID" in info
    assert "access token" in info
    markdown = " ".join(str(item.value) for item in at.markdown)
    assert ".football.cbssports.com" in markdown
    assert "not publicly viewable" in markdown
    token = next(w for w in at.text_input if w.key == "lh_cbs_token")
    assert token.value == ""
    captions = " ".join(str(item.value) for item in at.caption)
    assert "Do not paste it into chat" in captions
    assert "never logs or shared-caches it" in captions
    assert "no public-view importer" in captions
    assert "do not expose this value" in markdown
    assert "Authorization" in markdown
    assert "clears the field after a successful load" in markdown


def test_private_cbs_history_stays_in_session_and_clears_token(tmp_path):
    fixture = {
        "league_name": "Private CBS League",
        "provider": "CBS",
        "player_directory": {},
        "seasons": {"2025": {
            "league_id": "cbshelp",
            "draft_id": "",
            "status": "complete",
            "champion": {"username": "Alice", "team_name": "A Team"},
            "runner_up": {"username": "Bob", "team_name": "B Team"},
            "toilet_champion": {"username": "Bob", "team_name": "B Team"},
            "toilet_champions": [{"username": "Bob", "team_name": "B Team"}],
            "toilet_finalists": ["Alice", "Bob"],
            "toilet_bracket": ["Alice", "Bob"],
            "standings": [
                {
                    "roster_id": 1, "owner_id": "owner-a", "username": "Alice",
                    "team_name": "A Team", "wins": 1, "losses": 0,
                    "fpts": 110.0, "fpts_against": 90.0, "playoff_finish": 1,
                },
                {
                    "roster_id": 2, "owner_id": "owner-b", "username": "Bob",
                    "team_name": "B Team", "wins": 0, "losses": 1,
                    "fpts": 90.0, "fpts_against": 110.0, "playoff_finish": 2,
                },
            ],
            "matchups": [{
                "season": "2025", "week": 1, "is_playoff": False,
                "rid_a": "1", "score_a": 110.0,
                "rid_b": "2", "score_b": 90.0,
            }],
            "draft_picks": [],
            "roster_entries": [],
            "league_settings": {
                "total_rosters": 2, "roster_positions": [],
                "scoring_settings": {}, "waiver_type": 0, "waiver_budget": None,
            },
        }},
    }
    harness = tmp_path / "private_cbs_loaded.py"
    harness.write_text(
        f"import sys\nsys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import page_league_history as p\n"
        "p._OFFLINE = False\n"
        f"_fixture = {fixture!r}\n"
        "def _load(league_id, season, max_seasons=None, access_token=''):\n"
        "    assert league_id == 'cbshelp'\n"
        "    assert access_token == 'cbs-token-value'\n"
        "    return _fixture, None\n"
        "p._load_cbs_history_with_status = _load\n"
        "p.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    next(w for w in at.segmented_control if w.key == "lh_provider").set_value("CBS")
    at = at.run()
    next(w for w in at.text_input if w.key == "lh_league_id").set_value("cbshelp")
    next(w for w in at.number_input if w.key == "lh_cbs_season").set_value(2025)
    next(w for w in at.text_input if w.key == "lh_cbs_token").set_value("cbs-token-value")
    next(b for b in at.button if b.label == "Load league history").click()
    at = at.run()

    assert not at.exception, at.exception
    assert any(header.value == "Private CBS League" for header in at.header)
    assert next(w for w in at.text_input if w.key == "lh_cbs_token").value == ""
    assert any(
        "Stored only in this browser session" in str(caption.value)
        for caption in at.caption
    )


def test_league_history_validates_cbs_id_and_season():
    assert page_league_history._league_request_error(
        "CBS", "cbshelp", cbs_season=2025, cbs_token="token-value",
    ) is None
    assert "subdomain" in page_league_history._league_request_error(
        "CBS", "not a league", cbs_season=2025, cbs_token="token-value",
    )
    assert "does not look like" in page_league_history._league_request_error(
        "CBS", "www", cbs_season=2025, cbs_token="token-value",
    )
    assert "currently supports" in page_league_history._league_request_error(
        "CBS", "cbshelp", cbs_season=2017, cbs_token="token-value",
    )
    assert "access token" in page_league_history._league_request_error(
        "CBS", "cbshelp", cbs_season=2025, cbs_token="",
    )
    assert cbs_league_history.parse_league_ref(
        "https://cbshelp.football.cbssports.com/stats"
    ) == "cbshelp"


def test_private_cbs_requests_are_credentialed_and_never_shared_cached(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"statusCode": 200}'

        @staticmethod
        def json():
            return {"statusCode": 200, "body": {"league_details": {"name": "Private CBS"}}}

    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setattr(cbs_league_history.requests, "get", fake_get)
    for _ in range(2):
        payload = cbs_league_history._cbs_get_private(
            "cbshelp", 2025, "/league/details", "Authorization=Bearer session-token",
        )
        assert payload["body"]["league_details"]["name"] == "Private CBS"

    assert len(calls) == 2, "credentialed requests must bypass shared st.cache_data"
    assert calls[0]["headers"]["Authorization"] == "session-token"
    assert not hasattr(cbs_league_history._cbs_get_private, "clear")


def test_private_cbs_401_does_not_echo_token_values(monkeypatch):
    class Response:
        status_code = 401
        headers = {"content-type": "application/json"}
        text = ""

    monkeypatch.setattr(
        cbs_league_history.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )
    with pytest.raises(cbs_league_history.CbsLeagueError) as caught:
        cbs_league_history._cbs_get_private(
            "cbshelp", 2025, "/league/details", "sensitive-cbs-token",
        )
    message = str(caught.value)
    assert "Recopy the access token" in message
    assert "sensitive-cbs-token" not in message


def test_cbs_html_login_wall_is_treated_as_denied_access(monkeypatch):
    class Response:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        text = "<!DOCTYPE html><html><body>login</body></html>"

        @staticmethod
        def json():
            raise ValueError("not json")

    monkeypatch.setattr(
        cbs_league_history.requests,
        "get",
        lambda *args, **kwargs: Response(),
    )
    with pytest.raises(cbs_league_history.CbsLeagueError) as caught:
        cbs_league_history._cbs_get_private(
            "cbshelp", 2025, "/league/details", "session-token",
        )
    assert "Recopy the access token" in str(caught.value)


def test_cbs_season_normalizes_to_existing_history_schema():
    details = {
        "name": "Test CBS",
        "num_teams": 2,
        "current_period": 1,
        "regular_season_periods": 1,
        "playoff_periods": 0,
        "season_status": "postseason",
    }
    rules = {
        "transactions": {"add_drop_faab_starting_budget": {"value": "100"}},
        "roster": {
            "positions": [
                {"abbr": "QB", "max_active": 1},
                {"abbr": "RB", "max_active": 1},
            ],
            "statuses": [{"description": "Reserve Players", "max": 3}],
        },
        "scoring": {"categories": [
            {"abbr": "REC", "points": "0.5"},
            {"abbr": "PTD", "points": "4"},
        ]},
    }
    teams = [
        {"id": "1", "name": "A Team", "owners": [{"id": "owner-a", "name": "Alice"}]},
        {"id": "2", "name": "B Team", "owners": [{"id": "owner-b", "name": "Bob"}]},
    ]
    standings_teams = [
        {"id": "1", "wins": 1, "losses": 0, "points_scored": 110, "points_against": 90, "order": 1},
        {"id": "2", "wins": 0, "losses": 1, "points_scored": 90, "points_against": 110, "order": 2},
    ]
    schedule_periods = [{
        "id": "1", "label": "Week 1", "type": "Regular Season",
        "matchups": [{
            "id": 10, "type": "regular", "championship": 0,
            "home_team": {"id": "1", "points": "110", "result": "W"},
            "away_team": {"id": "2", "points": "90", "result": "L"},
        }],
    }]
    draft_picks_raw = [
        {
            "overall_pick": 1, "round": 1, "round_pick": 1,
            "player": {
                "id": "101", "fullname": "Runner One", "firstname": "Runner",
                "lastname": "One", "position": "RB",
            },
            "team": {"id": "1", "name": "A Team"},
        },
        {
            "overall_pick": 2, "round": 1, "round_pick": 2,
            "player": {
                "id": "202", "fullname": "Passer Two", "firstname": "Passer",
                "lastname": "Two", "position": "QB",
            },
            "team": {"id": "2", "name": "B Team"},
        },
    ]
    weekly = {1: {"body": {"rosters": {"teams": [
        {"id": "1", "players": [{
            "id": "101", "firstname": "Runner", "lastname": "One",
            "fullname": "Runner One", "position": "RB",
            "roster_status": "A", "roster_pos": "RB",
        }]},
        {"id": "2", "players": [{
            "id": "202", "firstname": "Passer", "lastname": "Two",
            "fullname": "Passer Two", "position": "QB",
            "roster_status": "RS", "roster_pos": "BN",
        }]},
    ]}}}}
    scoring = {"body": {"weekly_scoring": {"players": [
        {"id": "101", "periods": [{"period": 1, "score": "22.5"}]},
        {"id": "202", "periods": [{"period": 1, "score": "18"}]},
    ]}}}
    payload, players = cbs_league_history.normalize_season(
        "cbshelp", 2025, details, rules, teams, standings_teams,
        schedule_periods, draft_picks_raw, weekly, scoring,
    )
    assert payload["champion"]["username"] == "Alice"
    assert payload["runner_up"]["username"] == "Bob"
    assert payload["matchups"] == [{
        "season": "2025", "week": 1, "is_playoff": False,
        "rid_a": "1", "score_a": 110.0,
        "rid_b": "2", "score_b": 90.0,
    }]
    assert payload["roster_entries"][0]["players_points"]["101"] == 22.5
    assert payload["roster_entries"][0]["starters"] == ["101"]
    assert payload["roster_entries"][1]["starters"] == []
    assert payload["draft_picks"][0]["metadata"]["position"] == "RB"
    assert payload["league_settings"]["scoring_settings"] == {
        "rec": 0.5, "pass_td": 4.0,
    }
    assert payload["league_settings"]["waiver_type"] == 2
    assert players["202"]["position"] == "QB"


def test_rivalry_score_swatch_bands_and_card_html():
    locked = page_league_history._rivalry_score_swatch(12.0, locked=True)
    assert locked[0] == "#60A5FA"
    assert page_league_history._rivalry_score_swatch(70.0)[0] == "#35D08A"
    assert page_league_history._rivalry_score_swatch(50.0)[0] == "#FACC15"
    assert page_league_history._rivalry_score_swatch(49.9)[0] == "#F87171"
    html = page_league_history._rivalry_slate_card_html({
        "manager_a": "Alice",
        "manager_b": "Bob",
        "reason": "Playoff history",
        "locked": False,
        "rivalry_score": 71.2,
    })
    assert "RIVALRY SCORE" in html
    assert "71.2" in html
    assert "Alice vs Bob" in html
    assert "jsa-lh-card" in html
    assert "border-left:" not in html
    legend = page_league_history._rivalry_score_legend_html()
    assert "70+ fit" in legend
    assert "jsa-lh-legend" in legend
    css = (_HERE / "mobile.py").read_text(encoding="utf-8")
    assert ".jsa-lh-card" in css
    assert "[data-testid=\"stRadio\"]" in css
    assert "[data-testid=\"stMetricValue\"]" in css
    assert "[data-testid=\"stMetricValue\"] *" in css
    assert "white-space:normal" in css.replace(" ", "")
    assert "overflow-wrap:anywhere" in css.replace(" ", "")
    assert "text-overflow:ellipsis" not in css
    assert "white-space:pre-line" in css.replace(" ", "")
    assert "repeat(4,minmax(0,1fr))" in css.replace(" ", "")
    assert "::-webkit-scrollbar-thumb" in css
    assert "st-key-jsa-lh-leaderboard-cards" in css
    assert "st-key-jsa-lh-leaderboard-ties" in css
    assert "st-key-jsa-lh-report-cards" in css
    assert "3.9rem" in css
    assert "grid-auto-rows:1fr" in css.replace(" ", "")
    assert "st-key-jsa-lh-hof-cards" in css
    assert "st-key-jsa-scatter-desktop" in css
    assert "st-key-jsa-scatter-phone" in css
    assert "st-key-jsa-scatter-phone-league-matrix" in css
    assert "st-key-jsa-table-desktop" in css
    assert "st-key-jsa-table-phone" in css
    assert "st-key-jsa-gc" in css
    assert "jsa-gc-pick" in css
    assert "min-width:56rem" in css.replace(" ", "")
    assert "max-width:none" in css.replace(" ", "")
    assert "scrollbar-width:none" not in css.replace(" ", "")


def test_league_history_estimate_counts_linked_seasons(monkeypatch):
    leagues = {
        "current": {"season": "2026", "previous_league_id": "prior-1"},
        "prior-1": {"season": "2025", "previous_league_id": "prior-2"},
        "prior-2": {"season": "2024", "previous_league_id": "0"},
    }

    def _fake_get(url):
        return leagues.get(url.rsplit("/", 1)[-1])

    monkeypatch.setattr(page_league_history, "_sleeper_get", _fake_get)
    page_league_history._league_history_chain.clear()
    try:
        assert page_league_history._league_history_season_count("current") == 3
        assert page_league_history._history_load_estimate(3) == (6, 12)
        assert page_league_history._history_load_estimate(99) == (20, 40)
    finally:
        page_league_history._league_history_chain.clear()


def test_league_history_recent_mode_limits_heavy_season_fetches(monkeypatch):
    chain = [
        {"league_id": f"league-{year}", "season": str(year), "name": "Test"}
        for year in range(2026, 2021, -1)
    ]
    fetched = []

    monkeypatch.setattr(page_league_history, "_league_history_chain", lambda _lid: chain)

    def _fetch(league_id):
        fetched.append(league_id)
        year = league_id.rsplit("-", 1)[-1]
        return year, {"standings": [], "matchups": []}

    monkeypatch.setattr(page_league_history, "_fetch_one_season", _fetch)
    history = page_league_history._fetch_sleeper_history("current", max_seasons=3)
    assert list(history["seasons"]) == ["2026", "2025", "2024"]
    assert fetched == ["league-2026", "league-2025", "league-2024"]


def test_rookie_board_excludes_direct_pff_fields_and_explains_availability(tmp_path):
    """The public Rookie Board excludes direct PFF data and explains blank projections."""
    at = _render_page(tmp_path, "page_rookie_board")
    assert any(w.label == "Draft class" for w in at.selectbox)
    assert any(w.label == "Position" for w in at.selectbox)
    # Three tables since 2026-07-27: the rookie board itself, plus the collapsed
    # "college QBs/RBs/WRs/TEs not in this rookie class" views. ALL must stay free of direct PFF fields.
    assert len(at.dataframe) == 6

    banned_pff = {"PFF Grade", "PFF Grade (Percentile)", "PFF Efficiency",
                  "PFF Efficiency (Percentile)", "grades_pass", "btt_rate", "twp_rate",
                  "pressure_grade", "accuracy_pct", "grades_run"}
    tables = []
    for element in at.dataframe:
        value = element.value
        tables.append(value.data if hasattr(value, "data") else value)
    for table in tables:
        assert not banned_pff & set(table.columns),             f"direct PFF fields leaked into a public table: {banned_pff & set(table.columns)}"

    shown = max(tables, key=lambda table: len(table.columns))
    assert {"Draft-Capital Hit-%", "College Hit-%", "Full Hit-%", "College Talent",
            "Athleticism (Percentile)", "Production (Percentile)"} <= set(shown.columns)
    phone = min(
        (table for table in tables if "Full Hit-%" in table.columns),
        key=lambda table: len(table.columns),
    )
    assert list(phone.columns) == [
        "#", "Player", "Pos", "Pick", "Full Hit-%",
        "Proj (season ½-PPR)", "Diff vs Sleeper",
    ]

    for watch in tables:
        if "College Talent" in watch.columns and "Full Hit-%" not in watch.columns:
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
    page_league_history._league_history_chain.clear()
    page_league_history._fetch_one_season.clear()
    try:
        history = page_league_history._fetch_sleeper_history(league_id)
        assert history["seasons"]
        assert seen_workers == [page_league_history._MATCHUP_FETCH_WORKERS]
        assert seen_workers[0] <= 6
        assert history["seasons"]["2025"]["league_settings"]["waiver_type"] is None
    finally:
        page_league_history._league_history_chain.clear()
        page_league_history._fetch_one_season.clear()


def test_fetch_one_season_maps_losers_bracket_last_place(monkeypatch):
    league_id = "1255197436951932928"
    users = [
        {"user_id": "u6", "display_name": "LastPlace", "metadata": {}},
        {"user_id": "u12", "display_name": "ConsolationWinner", "metadata": {}},
        {"user_id": "u5", "display_name": "Runner", "metadata": {}},
        {"user_id": "u7", "display_name": "Third", "metadata": {}},
    ]
    rosters = [
        {"roster_id": 6, "owner_id": "u6", "settings": {"wins": 0, "losses": 1, "fpts": 10}},
        {"roster_id": 12, "owner_id": "u12", "settings": {"wins": 0, "losses": 1, "fpts": 20}},
        {"roster_id": 5, "owner_id": "u5", "settings": {"wins": 0, "losses": 1, "fpts": 30}},
        {"roster_id": 7, "owner_id": "u7", "settings": {"wins": 0, "losses": 1, "fpts": 40}},
    ]
    losers = [
        {"r": 1, "m": 1, "t1": 6, "t2": 12, "w": 12, "l": 6, "p": None},
        {"r": 1, "m": 2, "t1": 5, "t2": 7, "w": 5, "l": 7, "p": None},
        {"r": 2, "m": 3, "t1": 12, "t2": 5, "w": 12, "l": 5, "p": 1},
        {"r": 2, "m": 4, "t1": 6, "t2": 7, "w": 7, "l": 6, "p": 3},
    ]

    def _sleeper_get(url):
        if url.endswith(f"/league/{league_id}"):
            return {
                "name": "Test league", "season": "2025", "status": "complete",
                "settings": {"playoff_week_start": 15}, "previous_league_id": "0",
            }
        if url.endswith("/users"):
            return users
        if url.endswith("/rosters"):
            return rosters
        if url.endswith("/losers_bracket"):
            return losers
        return []

    class _Executor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

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

    monkeypatch.setattr(page_league_history, "_sleeper_get", _sleeper_get)
    monkeypatch.setattr(page_league_history._cf, "ThreadPoolExecutor", _Executor)
    monkeypatch.setattr(page_league_history.req, "get", lambda *_args, **_kwargs: _Response())
    page_league_history._fetch_one_season.clear()
    try:
        year, payload = page_league_history._fetch_one_season(league_id)
        assert year == "2025"
        assert payload["toilet_champion"]["username"] == "ConsolationWinner"
        assert payload["toilet_bracket"] == ["ConsolationWinner", "Runner"]
        assert payload["toilet_finalists"] == ["ConsolationWinner", "Runner"]
    finally:
        page_league_history._fetch_one_season.clear()


def test_infer_roster_owner_id_prefers_roster_then_draft_then_transactions():
    assert league_intel.infer_roster_owner_id(12, roster_owner_id="u12") == "u12"
    assert league_intel.infer_roster_owner_id(
        12, roster_owner_id=None,
        draft_picks=[{"roster_id": 12, "picked_by": "u-draft"}],
        transactions=[{"creator": "u-tx", "roster_ids": [12]}],
    ) == "u-draft"
    assert league_intel.infer_roster_owner_id(
        12, roster_owner_id=None,
        draft_picks=[{"roster_id": 12, "picked_by": ""}],
        transactions=[
            {"creator": "u-rare", "roster_ids": [12]},
            {"creator": "u-main", "roster_ids": [12]},
            {"creator": "u-main", "roster_ids": [12]},
        ],
    ) == "u-main"
    assert league_intel.infer_roster_owner_id(12, roster_owner_id=None) == ""


def test_fetch_recovers_departed_toilet_champion(monkeypatch):
    league_id = "1255197436951932928"
    users = [
        {"user_id": "u6", "display_name": "LastPlace", "metadata": {}},
        {"user_id": "u5", "display_name": "Runner", "metadata": {}},
        {"user_id": "u7", "display_name": "Third", "metadata": {}},
    ]
    rosters = [
        {"roster_id": 6, "owner_id": "u6", "settings": {"wins": 0, "losses": 1, "fpts": 10}},
        {"roster_id": 12, "owner_id": None, "settings": {"wins": 0, "losses": 1, "fpts": 20}},
        {"roster_id": 5, "owner_id": "u5", "settings": {"wins": 0, "losses": 1, "fpts": 30}},
        {"roster_id": 7, "owner_id": "u7", "settings": {"wins": 0, "losses": 1, "fpts": 40}},
    ]
    losers = [
        {"r": 2, "m": 3, "t1": 12, "t2": 5, "w": 12, "l": 5, "p": 1},
    ]

    def _sleeper_get(url):
        if url.endswith(f"/league/{league_id}"):
            return {
                "name": "Test league", "season": "2023", "status": "complete",
                "settings": {"playoff_week_start": 15}, "previous_league_id": "0",
            }
        if url.endswith("/users"):
            return users
        if url.endswith("/rosters"):
            return rosters
        if url.endswith("/losers_bracket"):
            return losers
        if url.endswith("/user/u-gone"):
            return {"user_id": "u-gone", "display_name": "Jaboom1", "username": "jaboom1"}
        return []

    class _Executor:
        def __init__(self, max_workers):
            self.max_workers = max_workers

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

    monkeypatch.setattr(page_league_history, "_sleeper_get", _sleeper_get)
    monkeypatch.setattr(page_league_history._cf, "ThreadPoolExecutor", _Executor)
    monkeypatch.setattr(page_league_history.req, "get", lambda *_args, **_kwargs: _Response())
    monkeypatch.setattr(
        page_league_history, "_fetch_season_transactions",
        lambda _league_id: [{"creator": "u-gone", "roster_ids": [12]}],
    )
    page_league_history._fetch_one_season.clear()
    try:
        year, payload = page_league_history._fetch_one_season(league_id)
        assert year == "2023"
        assert payload["toilet_champion"]["username"] == "Jaboom1"
        standing = next(
            row for row in payload["standings"] if str(row["roster_id"]) == "12"
        )
        assert standing["username"] == "Jaboom1"
        assert standing["owner_id"] == "u-gone"
    finally:
        page_league_history._fetch_one_season.clear()


def test_league_intelligence_normalizes_drafts_and_explains_room_tendencies():
    seasons = {}
    for season in ("2023", "2024", "2025"):
        seasons[season] = {
            "draft_id": f"draft-{season}",
            "draft_picks": [
                {"pick_no": 1, "round": 1, "pick_in_round": 1, "draft_slot": 1,
                 "picked_by": "u1", "player_id": f"rb-{season}",
                 "metadata": {"first_name": "Early", "last_name": "Runner", "position": "RB"}},
                {"pick_no": 2, "round": 1, "pick_in_round": 2, "draft_slot": 2,
                 "picked_by": "u2", "player_id": f"wr-{season}",
                 "metadata": {"first_name": "Early", "last_name": "Receiver", "position": "WR"}},
                {"pick_no": 13, "round": 2, "pick_in_round": 1, "draft_slot": 2,
                 "picked_by": "u2", "player_id": f"te-{season}",
                 "metadata": {"first_name": "First", "last_name": "Tight End", "position": "TE"}},
                {"pick_no": 25, "round": 3, "pick_in_round": 1, "draft_slot": 1,
                 "picked_by": "u1", "player_id": f"qb-{season}",
                 "metadata": {"first_name": "First", "last_name": "Quarterback", "position": "QB"}},
                {"pick_no": 37, "round": 4, "pick_in_round": 1, "draft_slot": 1,
                 "picked_by": "u1", "player_id": f"qb2-{season}",
                 "metadata": {"first_name": "Backup", "last_name": "Quarterback", "position": "QB"}},
                {"pick_no": 38, "round": 4, "pick_in_round": 2, "draft_slot": 2,
                 "picked_by": "u2", "player_id": f"te2-{season}",
                 "metadata": {"first_name": "Backup", "last_name": "Tight End", "position": "TE"}},
            ],
        }

    picks = league_intel.draft_pick_frame(seasons)
    managers = league_intel.manager_season_frame(picks)
    construction = league_intel.roster_construction_frame(managers)
    timing = league_intel.first_pick_timing_frame(picks)

    assert len(picks) == 18
    assert set(timing["position"]) == {"QB", "TE"}
    assert set(timing[timing["position"] == "QB"]["round"]) == {3}
    assert set(timing[timing["position"] == "TE"]["round"]) == {2}
    assert construction["avg_qb"].eq(1).all()
    assert construction["avg_te"].eq(1).all()
    insights = league_intel.draft_insights(picks, managers, "u1")
    assert any(item["title"] == "Your early-round fingerprint" for item in insights)
    assert all(
        {"finding", "meaning", "evidence", "confidence", "bullet"} <= set(item)
        for item in insights
    )
    assert len(insights) <= 5


def test_league_history_defaults_to_draft_and_roster_insights():
    assert page_league_history._LEAGUE_HISTORY_TABS[0] == "🧠 Draft & Roster Insights"
    assert page_league_history._LEAGUE_HISTORY_TABS[1] == "🏆 All-Time Leaderboard"
    assert page_league_history._LEAGUE_HISTORY_TABS[-1] == "📊 Consistency & Luck"
    assert "📈 Score Trends" not in page_league_history._LEAGUE_HISTORY_TABS
    assert len(page_league_history._LEAGUE_HISTORY_TABS) == 6


def test_insights_render_accepts_transaction_loader():
    import inspect
    import league_insights_view
    params = inspect.signature(league_insights_view.render).parameters
    assert "transaction_loader" in params


def test_reload_if_stale_picks_up_a_new_file_on_disk(tmp_path):
    import page_common

    path = tmp_path / "stale_helper.py"
    path.write_text("VALUE = 1\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        import stale_helper
        stale_helper.__joscho_source_mtime_ns__ = 0
        path.write_text("VALUE = 2\n", encoding="utf-8")
        refreshed = page_common.reload_if_stale(stale_helper)
        assert refreshed.VALUE == 2
    finally:
        sys.modules.pop("stale_helper", None)
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_manager_leaderboard_adjusts_scores_within_each_league_week():
    seasons = {
        "2024": {
            "standings": [
                {"username": "Alice", "wins": 2, "losses": 0, "playoff_finish": 1},
                {"username": "Bob", "wins": 0, "losses": 2, "playoff_finish": 2},
            ],
            "champion": {"username": "Alice"},
            "runner_up": {"username": "Bob"},
        },
        "2025": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 1, "playoff_finish": 2},
                {"username": "Bob", "wins": 1, "losses": 1, "playoff_finish": 1},
            ],
            "champion": {"username": "Bob"},
            "runner_up": {"username": "Alice"},
        },
    }
    games = [
        {"season": "2024", "week": 1, "username": "Alice", "score": 110, "is_playoff": False},
        {"season": "2024", "week": 1, "username": "Bob", "score": 90, "is_playoff": False},
        {"season": "2024", "week": 2, "username": "Alice", "score": 80, "is_playoff": False},
        {"season": "2024", "week": 2, "username": "Bob", "score": 120, "is_playoff": False},
        {"season": "2024", "week": 15, "username": "Alice", "score": 200, "is_playoff": True},
    ]

    leaders = league_intel.manager_leaderboard_frame(seasons, games).set_index("manager")
    assert leaders.loc["Alice", "win_pct"] == 75.0
    assert leaders.loc["Alice", "titles"] == 1
    assert leaders.loc["Alice", "finals"] == 2
    assert leaders.loc["Alice", "seasons"] == 2
    assert leaders.loc["Alice", "avg_score"] == 95.0
    assert leaders.loc["Alice", "avg_above_league"] == -5.0
    assert leaders.loc["Bob", "avg_above_league"] == 5.0
    assert leaders.loc["Alice", "games"] == 2
    assert leaders.loc["Alice", "total_points"] == 190.0
    assert leaders.loc["Bob", "total_points"] == 210.0
    assert leaders.loc["Alice", "active_playoff_streak"] == 2
    assert leaders.loc["Bob", "active_playoff_streak"] == 2
    assert leaders.loc["Alice", "toilet_titles"] == 0
    assert leaders.loc["Bob", "toilet_appearances"] == 0


def test_tied_leaders_share_a_headline_without_win_pct_tiebreak():
    frame = pd.DataFrame([
        {"manager": "Bob", "titles": 2, "win_pct": 40.0,
         "avg_above_league": 1.0, "seasons": 4},
        {"manager": "Alice", "titles": 2, "win_pct": 70.0,
         "avg_above_league": 1.0, "seasons": 4},
        {"manager": "Carol", "titles": 1, "win_pct": 70.0,
         "avg_above_league": 3.0, "seasons": 2},
    ])
    names, value = league_intel.tied_leaders(frame, "titles", min_value=1)
    assert names == ["Alice", "Bob"]
    assert value == 2.0
    names, value = league_intel.tied_leaders(frame, "win_pct")
    assert names == ["Alice", "Carol"]
    names, value = league_intel.tied_leaders(frame, "avg_above_league")
    assert names == ["Carol"]
    assert value == 3.0
    names, value = league_intel.tied_leaders(frame, "avg_above_league", ascending=True)
    assert names == ["Alice", "Bob"]
    assert value == 1.0
    names, value = league_intel.tied_leaders(frame, "seasons")
    assert names == ["Alice", "Bob"]
    assert league_intel.tied_leaders(frame, "titles", min_value=3) == ([], None)
    empty = pd.DataFrame(columns=["manager", "titles"])
    assert league_intel.tied_leaders(empty, "titles") == ([], None)
    assert league_intel.format_tied_names(["Alice"]) == "Alice"
    assert league_intel.format_tied_names(["Alice", "Bob"]) == "Alice & Bob"
    assert league_intel.format_tied_names(["Alice", "Bob", "Carol"]) == "Alice, Bob +1"
    assert league_intel.scorecard_headline(["Alice", "Bob"], flip_at=3) == "Alice\nBob"
    assert league_intel.scorecard_headline(["VeryLongManagerName"]) == "VeryLongManagerName"
    assert league_intel.scorecard_headline(
        ["Alice", "Bob", "Carol"], flip_at=3,
    ) == "3-way tie"
    assert league_intel.format_name_list(
        ["Alice", "Bob", "Carol"]
    ) == "Alice, Bob, and Carol"
    assert league_intel.n_way_tie_bullets([
        ("Most Titles", ["MilanPandey", "awf3", "theted123"]),
        ("Longest Active Playoff Streak",
         ["GarnerRandazzo", "JoScho", "awf3", "menglish8"]),
        ("Most Toilet Bowl Titles", ["Jaboom1", "joshuasurprise", "theted123"]),
    ]) == (
        "- Most Titles is a 3-way tie: MilanPandey, awf3, and theted123.\n"
        "- Longest Active Playoff Streak is a 4-way tie: "
        "GarnerRandazzo, JoScho, awf3, and menglish8.\n"
        "- Most Toilet Bowl Titles is a 3-way tie: "
        "Jaboom1, joshuasurprise, and theted123."
    )


def test_active_playoff_streak_starts_at_latest_decided_season():
    seasons = {
        "2023": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0, "playoff_finish": 3},
                {"username": "Bob", "wins": 1, "losses": 0, "playoff_finish": 4},
                {"username": "Carol", "wins": 0, "losses": 1, "playoff_finish": None},
            ],
        },
        "2024": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0, "playoff_finish": 1},
                {"username": "Bob", "wins": 1, "losses": 0, "playoff_finish": 2},
                {"username": "Carol", "wins": 1, "losses": 0, "playoff_finish": 3},
            ],
        },
        "2025": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0, "playoff_finish": 2},
                {"username": "Bob", "wins": 0, "losses": 1, "playoff_finish": None},
                {"username": "Carol", "wins": 1, "losses": 0, "playoff_finish": 4},
            ],
        },
        "2026": {
            "standings": [
                {"username": "Alice", "wins": 0, "losses": 0, "playoff_finish": None},
                {"username": "Bob", "wins": 0, "losses": 0, "playoff_finish": None},
                {"username": "Carol", "wins": 0, "losses": 0, "playoff_finish": None},
            ],
        },
    }
    streaks = league_intel.active_playoff_streaks(seasons)
    assert streaks["Alice"] == 3
    assert streaks["Bob"] == 0
    assert streaks["Carol"] == 2
    names, value = league_intel.tied_leaders(
        league_intel.manager_leaderboard_frame(seasons, []),
        "active_playoff_streak",
        min_value=1,
    )
    assert names == ["Alice"]
    assert value == 3.0


def test_active_playoff_streak_three_way_tie_uses_title_rule():
    seasons = {
        "2025": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0, "playoff_finish": 1},
                {"username": "Bob", "wins": 1, "losses": 0, "playoff_finish": 2},
                {"username": "Carol", "wins": 1, "losses": 0, "playoff_finish": 3},
            ],
        },
    }
    names, value = league_intel.tied_leaders(
        league_intel.manager_leaderboard_frame(seasons, []),
        "active_playoff_streak",
        min_value=1,
    )
    assert names == ["Alice", "Bob", "Carol"]
    assert value == 1.0
    assert league_intel.scorecard_headline(names, flip_at=3) == "3-way tie"


def test_losers_bracket_last_place_is_highest_assigned_finish():
    bracket = [
        {"r": 1, "m": 1, "t1": 6, "t2": 12, "w": 12, "l": 6, "p": None},
        {"r": 1, "m": 2, "t1": 5, "t2": 7, "w": 5, "l": 7, "p": None},
        {"r": 2, "m": 3, "t1": 12, "t2": 5, "w": 12, "l": 5, "p": 1},
        {"r": 2, "m": 4, "t1": 6, "t2": 7, "w": 7, "l": 6, "p": 3},
    ]
    assert league_intel.last_place_roster_ids(bracket) == ["6"]
    assert league_intel.bracket_title_roster_ids(bracket) == ["12"]
    assert league_intel.bracket_finals_roster_ids(bracket) == ["12", "5"]
    assert league_intel.bracket_roster_ids(bracket) == {"5", "6", "7", "12"}
    assert league_intel.bracket_placement_ranks(bracket) == {
        "12": 1, "5": 2, "7": 3, "6": 4,
    }
    assert league_intel.last_place_roster_ids([]) == []
    assert league_intel.bracket_roster_ids(None) == set()


def test_toilet_scorecards_count_last_place_and_bracket_appearances():
    seasons = {
        "2023": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0},
                {"username": "Bob", "wins": 0, "losses": 1},
                {"username": "Carol", "wins": 0, "losses": 1},
            ],
            "champion": {"username": "Alice"},
            "toilet_champion": {"username": "Bob"},
            "toilet_bracket": ["Bob", "Carol"],
        },
        "2024": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0},
                {"username": "Bob", "wins": 0, "losses": 1},
                {"username": "Carol", "wins": 0, "losses": 1},
            ],
            "champion": {"username": "Alice"},
            "toilet_champions": [{"username": "Carol"}],
            "toilet_bracket": ["Bob", "Carol"],
        },
        "2025": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0},
                {"username": "Bob", "wins": 1, "losses": 0},
                {"username": "Carol", "wins": 0, "losses": 1},
            ],
            "champion": {"username": "Bob"},
            "toilet_champion": {"username": "Carol"},
            "toilet_bracket": ["Carol"],
        },
    }
    leaders = league_intel.manager_leaderboard_frame(seasons, []).set_index("manager")
    assert leaders.loc["Alice", "titles"] == 2
    assert leaders.loc["Bob", "toilet_titles"] == 1
    assert leaders.loc["Carol", "toilet_titles"] == 2
    assert leaders.loc["Bob", "toilet_appearances"] == 2
    assert leaders.loc["Carol", "toilet_appearances"] == 3
    assert leaders.loc["Alice", "toilet_appearances"] == 0
    names, value = league_intel.tied_leaders(leaders.reset_index(), "toilet_titles", min_value=1)
    assert names == ["Carol"]
    assert value == 2.0
    names, value = league_intel.tied_leaders(
        leaders.reset_index(), "toilet_appearances", min_value=1,
    )
    assert names == ["Carol"]
    assert value == 3.0
    assert league_intel.scorecard_headline(
        ["Alice", "Bob", "Carol"], flip_at=3,
    ) == "3-way tie"


def test_three_toilet_champs_at_one_are_an_n_way_tie():
    seasons = {
        "2023": {
            "toilet_champion": {"username": "Jaboom1"},
            "standings": [{"username": "Jaboom1", "wins": 0, "losses": 1}],
        },
        "2024": {
            "toilet_champion": {"username": "theted123"},
            "standings": [{"username": "theted123", "wins": 0, "losses": 1}],
        },
        "2025": {
            "toilet_champion": {"username": "joshuasurprise"},
            "standings": [{"username": "joshuasurprise", "wins": 0, "losses": 1}],
        },
    }
    leaders = league_intel.manager_leaderboard_frame(seasons, [])
    names, value = league_intel.tied_leaders(leaders, "toilet_titles", min_value=1)
    assert names == ["Jaboom1", "joshuasurprise", "theted123"]
    assert value == 1.0
    assert league_intel.scorecard_headline(names, flip_at=3) == "3-way tie"


def test_lowest_ppg_scorecard_needs_more_than_two_seasons():
    seasons = {
        "2023": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0},
                {"username": "Bob", "wins": 0, "losses": 1},
                {"username": "Carol", "wins": 0, "losses": 1},
            ],
        },
        "2024": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0},
                {"username": "Bob", "wins": 0, "losses": 1},
                {"username": "Carol", "wins": 0, "losses": 1},
            ],
        },
        "2025": {
            "standings": [
                {"username": "Alice", "wins": 1, "losses": 0},
                {"username": "Bob", "wins": 0, "losses": 1},
            ],
        },
    }
    games = []
    for season, alice, bob, carol in (
        ("2023", 110.0, 90.0, 40.0),
        ("2024", 100.0, 80.0, 50.0),
        ("2025", 90.0, 70.0, None),
    ):
        games.append({
            "season": season, "week": 1, "username": "Alice", "score": alice,
            "is_playoff": False,
        })
        games.append({
            "season": season, "week": 1, "username": "Bob", "score": bob,
            "is_playoff": False,
        })
        if carol is not None:
            games.append({
                "season": season, "week": 1, "username": "Carol", "score": carol,
                "is_playoff": False,
            })
    leaders = league_intel.manager_leaderboard_frame(seasons, games)
    established = leaders[leaders["seasons"].gt(2)]
    names, value = league_intel.tied_leaders(established, "avg_score", ascending=True)
    assert names == ["Bob"]
    assert value == 80.0
    names, value = league_intel.tied_leaders(leaders, "avg_score", ascending=True)
    assert names == ["Carol"]
    assert leaders.set_index("manager").loc["Carol", "seasons"] == 2


def test_matchup_record_book_uses_weekly_all_play_for_luck():
    games = [
        {"season": "2025", "week": 1, "username": "Alice", "score": 110,
         "opp": "Bob", "opp_score": 100, "won": True, "is_playoff": False},
        {"season": "2025", "week": 1, "username": "Bob", "score": 100,
         "opp": "Alice", "opp_score": 110, "won": False, "is_playoff": False},
        {"season": "2025", "week": 1, "username": "Carol", "score": 150,
         "opp": "Dan", "opp_score": 140, "won": True, "is_playoff": False},
        {"season": "2025", "week": 1, "username": "Dan", "score": 140,
         "opp": "Carol", "opp_score": 150, "won": False, "is_playoff": False},
        {"season": "2025", "week": 2, "username": "Alice", "score": 4,
         "opp": "Bob", "opp_score": 3, "won": True, "is_playoff": False},
    ]

    matchups = league_intel.matchup_record_frame(games)
    assert len(matchups) == 2
    alice = matchups.set_index("winner").loc["Alice"]
    carol = matchups.set_index("winner").loc["Carol"]
    assert alice["combined"] == 210
    assert alice["margin"] == 10
    assert alice["all_play_wins"] == 1
    assert alice["all_play_opponents"] == 3
    assert alice["all_play_win_pct"] == 33.3
    assert carol["all_play_win_pct"] == 100.0


def test_scorecard_highlights_cover_every_hall_of_fame_card():
    games = []
    for username, opp, score, opp_score, week in (
        ("Alice", "Bob", 160.0, 40.0, 1),
        ("Bob", "Alice", 40.0, 160.0, 1),
        ("Carol", "Dan", 100.5, 100.4, 2),
        ("Dan", "Carol", 100.4, 100.5, 2),
    ):
        games.append({
            "season": "2025", "week": week, "username": username,
            "score": score, "opp": opp, "opp_score": opp_score,
            "won": score > opp_score, "is_playoff": False,
        })
    matchups = league_intel.matchup_record_frame(games)
    blowout = matchups.loc[matchups["margin"].idxmax()].to_dict()
    closest = matchups.loc[matchups["margin"].idxmin()].to_dict()
    highest_game = matchups.loc[matchups["combined"].idxmax()].to_dict()
    lowest_game = matchups.loc[matchups["combined"].idxmin()].to_dict()
    luckiest = matchups.sort_values(
        ["all_play_win_pct", "winner_score"], ascending=[True, True]
    ).iloc[0].to_dict()
    labels = league_intel.scorecard_highlight_labels(matchups, [
        ({"season": "2025", "week": 1, "username": "Alice", "opp": "Bob"}, "Highest Score"),
        ({"season": "2025", "week": 1, "username": "Bob", "opp": "Alice"}, "Most Painful Loss"),
        (blowout, "Biggest Blowout"),
        (closest, "Closest Game"),
        ({"season": "2025", "week": 1, "username": "Bob", "opp": "Alice"}, "Lowest Score"),
        (luckiest, "Luckiest Win"),
        (highest_game, "Highest-Scoring Game"),
        (lowest_game, "Lowest-Scoring Game"),
    ])
    named = [name for names in labels.values() for name in names]
    assert set(named) == {
        "Highest Score", "Most Painful Loss", "Biggest Blowout", "Closest Game",
        "Lowest Score", "Luckiest Win", "Highest-Scoring Game", "Lowest-Scoring Game",
    }
    assert len(named) == 8
    assert len(labels) == 2
    week_one = league_intel.matchup_index_for_record(
        matchups, {"season": "2025", "week": 1, "username": "Alice", "opp": "Bob"},
    )
    week_two = league_intel.matchup_index_for_record(
        matchups, {"season": "2025", "week": 2, "username": "Carol", "opp": "Dan"},
    )
    assert "Highest Score" in labels[week_one]
    assert "Closest Game" in labels[week_two]


def test_hall_of_fame_delta_is_matchup_week_and_both_scores():
    assert league_intel.hall_of_fame_delta({
        "season": "2023", "week": 13, "winner": "HHayes9", "loser": "theted123",
        "winner_score": 155, "loser_score": 50, "is_tie": False,
    }) == "HHayes9 def. theted123 · 2023 Wk 13 (155 - 50)"
    assert league_intel.hall_of_fame_delta({
        "season": "2023", "week": 13, "username": "menglish8",
        "score": 147.1, "opp": "HHayes9", "opp_score": 155.0, "won": False,
    }) == "HHayes9 def. menglish8 · 2023 Wk 13 (155 - 147.1)"
    assert league_intel.hall_of_fame_delta({
        "season": "2024", "week": 1, "team_a": "Alice", "team_b": "Bob",
        "winner": "Tie", "loser": "Tie", "winner_score": 100.0,
        "loser_score": 100.0, "is_tie": True,
    }) == "Alice tied Bob · 2024 Wk 1 (100 - 100)"
    assert league_intel.hall_of_fame_delta(None) is None


def test_hall_of_fame_era_caption_uses_that_season_average():
    played = [
        {"season": "2023", "score": 155.0},
        {"season": "2023", "score": 50.0},
        {"season": "2024", "score": 200.0},
    ]
    assert league_intel.hall_of_fame_era_caption(
        {"season": "2023", "score": 155.0}, played,
    ) == "The 155 high in 2023 came in a year whose league average was 102.5."
    assert league_intel.hall_of_fame_era_caption(None, played) is None


def test_rivalry_summary_tracks_series_scoring_playoffs_and_streaks():
    games = []
    for season, week, alice_score, bob_score, playoff in (
        ("2024", 1, 100, 90, False),
        ("2024", 2, 100, 110, False),
        ("2025", 15, 100, 120, True),
    ):
        games.extend([
            {"season": season, "week": week, "username": "Alice",
             "score": alice_score, "opp": "Bob", "opp_score": bob_score,
             "won": alice_score > bob_score, "is_playoff": playoff},
            {"season": season, "week": week, "username": "Bob",
             "score": bob_score, "opp": "Alice", "opp_score": alice_score,
             "won": bob_score > alice_score, "is_playoff": playoff},
        ])

    matchups = league_intel.matchup_record_frame(games)
    rivalry = league_intel.rivalry_summary_frame(matchups).iloc[0]
    assert rivalry["manager_a"] == "Alice"
    assert rivalry["manager_b"] == "Bob"
    assert rivalry["games"] == 3
    assert rivalry["manager_a_wins"] == 1
    assert rivalry["manager_b_wins"] == 2
    assert rivalry["manager_a_avg_score"] == 100.0
    assert rivalry["manager_b_avg_score"] == 106.67
    assert rivalry["avg_point_diff"] == -6.67
    assert rivalry["playoff_meetings"] == 1
    assert rivalry["current_streak_manager"] == "Bob"
    assert rivalry["current_streak"] == 2
    assert rivalry["closest_margin"] == 10
    assert rivalry["largest_margin"] == 20


def test_rivalry_week_scores_modes_and_uses_stable_unique_labels():
    identities = {"u1": "Alex", "u2": "Alex", "u3": "Casey", "u4": "Drew"}
    labels = league_intel.manager_display_labels(identities)
    assert labels["u1"] != labels["u2"]
    assert labels["u3"] == "Casey"

    games = []
    for season, week, alex_score, casey_score, playoff in (
        ("2023", 1, 101, 99, False),
        ("2023", 15, 112, 115, True),
        ("2024", 2, 120, 116, False),
        ("2024", 16, 104, 108, True),
        ("2025", 4, 130, 126, False),
        ("2025", 8, 99, 101, False),
    ):
        games.extend([
            {"season": season, "week": week, "username": labels["u1"],
             "score": alex_score, "opp": labels["u3"], "opp_score": casey_score,
             "won": alex_score > casey_score, "is_playoff": playoff},
            {"season": season, "week": week, "username": labels["u3"],
             "score": casey_score, "opp": labels["u1"], "opp_score": alex_score,
             "won": casey_score > alex_score, "is_playoff": playoff},
        ])

    matchups = league_intel.matchup_record_frame(games)
    managers = list(labels.values())
    classic = league_intel.rivalry_pair_score_frame(
        matchups, managers, "Classic Rivalries"
    )
    fresh = league_intel.rivalry_pair_score_frame(matchups, managers, "Fresh Blood")

    established_pair = frozenset((labels["u1"], labels["u3"]))
    classic_by_pair = {
        frozenset((row["manager_a"], row["manager_b"])): row
        for _, row in classic.iterrows()
    }
    fresh_by_pair = {
        frozenset((row["manager_a"], row["manager_b"])): row
        for _, row in fresh.iterrows()
    }
    assert len(classic) == 6
    assert classic_by_pair[established_pair]["games"] == 6
    assert classic_by_pair[established_pair]["playoff_meetings"] == 2
    assert classic_by_pair[established_pair]["rivalry_score"] > classic[
        classic["games"].eq(0)
    ]["rivalry_score"].max()
    assert fresh_by_pair[established_pair]["rivalry_score"] < fresh[
        fresh["games"].eq(0)
    ]["rivalry_score"].min()
    assert "First recorded meeting" in fresh[fresh["games"].eq(0)].iloc[0]["reason"]


def test_rivalry_week_slate_optimizes_globally_and_honors_locks():
    # Greedy AB first would total only 101. The global optimum is AC + BD = 198.
    scores = pd.DataFrame([
        {"manager_a": "A", "manager_b": "B", "rivalry_score": 100.0, "reason": "AB"},
        {"manager_a": "A", "manager_b": "C", "rivalry_score": 99.0, "reason": "AC"},
        {"manager_a": "A", "manager_b": "D", "rivalry_score": 2.0, "reason": "AD"},
        {"manager_a": "B", "manager_b": "C", "rivalry_score": 2.0, "reason": "BC"},
        {"manager_a": "B", "manager_b": "D", "rivalry_score": 99.0, "reason": "BD"},
        {"manager_a": "C", "manager_b": "D", "rivalry_score": 1.0, "reason": "CD"},
    ])

    slate = league_intel.rivalry_week_slate_frame(scores)
    pairs = {
        frozenset((row["manager_a"], row["manager_b"]))
        for _, row in slate.iterrows()
    }
    assert pairs == {frozenset(("A", "C")), frozenset(("B", "D"))}
    assert slate["rivalry_score"].sum() == 198.0

    locked = league_intel.rivalry_week_slate_frame(
        scores,
        locked_pairs=[("A", "B")],
        avoided_pairs=[("C", "D")],
    )
    locked_pairs = {
        frozenset((row["manager_a"], row["manager_b"]))
        for _, row in locked.iterrows()
    }
    assert locked_pairs == {frozenset(("A", "B")), frozenset(("C", "D"))}
    assert bool(locked.loc[locked["reason"].eq("AB"), "locked"].iloc[0])


def test_manager_performance_uses_peer_week_context_and_excludes_playoffs():
    games = []
    weekly = {
        1: {"Alice": (95, "Bob", 90), "Bob": (90, "Alice", 95),
            "Carol": (130, "Dan", 85), "Dan": (85, "Carol", 130)},
        2: {"Alice": (110, "Bob", 120), "Bob": (120, "Alice", 110),
            "Carol": (90, "Dan", 80), "Dan": (80, "Carol", 90)},
    }
    for week, managers in weekly.items():
        for manager, (score, opponent, opponent_score) in managers.items():
            games.append({
                "season": "2025", "week": week, "username": manager,
                "score": score, "opp": opponent, "opp_score": opponent_score,
                "won": score > opponent_score, "is_playoff": False,
            })
    games.extend([
        {"season": "2025", "week": 15, "username": "Alice", "score": 200,
         "opp": "Bob", "opp_score": 100, "won": True, "is_playoff": True},
        {"season": "2025", "week": 15, "username": "Bob", "score": 100,
         "opp": "Alice", "opp_score": 200, "won": False, "is_playoff": True},
    ])

    context = league_intel.weekly_score_context_frame(games)
    assert len(context) == 8
    alice_week_one = context[
        context["manager"].eq("Alice") & context["week"].eq(1)
    ].iloc[0]
    alice_week_two = context[
        context["manager"].eq("Alice") & context["week"].eq(2)
    ].iloc[0]
    assert alice_week_one["league_average"] == 100.0
    assert alice_week_one["league_median"] == 92.5
    assert alice_week_one["adjusted_score"] == -5.0
    assert alice_week_two["league_average"] == 100.0
    assert alice_week_two["league_median"] == 100.0
    assert alice_week_two["adjusted_score"] == 10.0

    performance = league_intel.manager_performance_frame(games).set_index("manager")
    alice = performance.loc["Alice"]
    assert alice["games"] == 2
    assert alice["wins"] == 1
    assert alice["losses"] == 1
    assert alice["win_pct"] == 50.0
    assert alice["avg_score"] == 102.5
    assert alice["avg_above_league"] == 2.5
    assert alice["std_dev"] == 10.61
    assert alice["lucky_wins"] == 1
    assert alice["unlucky_losses"] == 1

    consistency = league_intel.consistency_luck_frame(games).set_index("manager")
    alice_luck = consistency.loc["Alice"]
    carol_luck = consistency.loc["Carol"]
    assert alice_luck["games"] == 2
    assert alice_luck["avg_above_league"] == 2.5
    assert alice_luck["volatility"] == 10.61
    assert alice_luck["actual_wins"] == 1.0
    assert alice_luck["expected_wins"] == 1.33
    assert alice_luck["luck_delta"] == -0.33
    assert alice_luck["below_avg_wins"] == 1
    assert alice_luck["above_avg_losses"] == 1
    assert carol_luck["luck_delta"] == 0.67


def test_unlabeled_scatter_copy_keeps_hover_text_and_drops_on_chart_names():
    import plotly.graph_objects as go

    fig = go.Figure(go.Scatter(
        x=[50, 60], y=[1.0, -0.5],
        text=["Alice", "Bob"],
        mode="markers+text",
    ))
    fig.add_trace(go.Scatter(x=[40], y=[0], mode="markers", name="plain"))
    phone = page_common.unlabeled_scatter_copy(fig)
    assert phone.data[0].mode == "markers"
    assert list(phone.data[0].text) == ["Alice", "Bob"]
    assert phone.data[1].mode == "markers"
    assert fig.data[0].mode == "markers+text"


def test_league_matrix_phone_copy_is_taller_and_drops_cell_records():
    managers = ["Alice", "Bob", "Carol"]
    values = [[None, 10, -5], [-10, None, 20], [5, -20, None]]
    text = [["—", "2-1", "0-2"], ["1-2", "—", "3-0"], ["2-0", "0-3", "—"]]
    games = [[0, 3, 2], [3, 0, 3], [2, 3, 0]]
    desktop = page_league_history._league_matrix_figure(
        managers, values, text, games, phone=False,
    )
    phone = page_league_history._league_matrix_figure(
        managers, values, text, games, phone=True,
    )
    twelve = page_league_history._league_matrix_figure(
        [f"M{i}" for i in range(12)],
        [[None] * 12 for _ in range(12)],
        [["—"] * 12 for _ in range(12)],
        [[0] * 12 for _ in range(12)],
        phone=True,
    )
    assert desktop.data[0].texttemplate == "%{text}"
    assert not phone.data[0].texttemplate
    assert phone.data[0].showscale is False
    assert phone.layout.height > desktop.layout.height
    assert phone.layout.autosize is False
    assert phone.layout.width >= 760
    assert twelve.layout.width >= 888
    assert twelve.layout.width > phone.layout.width
    assert desktop.layout.width in (None, 0)
    assert list(phone.data[0].text[0]) == text[0]


def test_report_cards_use_aligned_scorecard_container():
    src = (_HERE / "site_pages" / "page_league_history.py").read_text(encoding="utf-8")
    assert 'key="jsa-lh-report-cards"' in src


def test_schedule_luck_chart_keeps_bar_labels_off_the_axis_title():
    """Phone overlap: a one-line x-axis title ran into outside bar labels."""
    fig = page_league_history._schedule_luck_figure(pd.DataFrame({
        "manager": ["LongManagerName", "Bo"],
        "luck_delta": [-1.25, 1.40],
        "actual_wins": [8.0, 12.0],
        "expected_wins": [9.25, 10.60],
        "actual_win_pct": [50.0, 75.0],
        "expected_win_pct": [57.8, 66.3],
        "below_avg_wins": [1, 2],
        "above_avg_losses": [2, 0],
        "games": [16, 16],
    }))
    labels = list(fig.data[0].text)
    assert labels == ["8.0 / 9.2", "12.0 / 10.6"]
    assert all("actual" not in label.lower() for label in labels)
    axis_title = fig.layout.xaxis.title.text
    assert "<br>" in axis_title
    assert fig.layout.margin.r <= 110
    assert fig.layout.margin.b >= 80
    assert fig.layout.xaxis.automargin is True


def test_loaded_league_history_renders_insights_first_and_chart_first_leaderboard(tmp_path):
    fixture = {
        "league_name": "Test League",
        "seasons": {
            "2025": {
                "league_id": "1255197436951932928",
                "draft_id": "draft-2025",
                "status": "complete",
                "champion": {"username": "Alice", "team_name": "A Team"},
                "runner_up": {"username": "Bob", "team_name": "B Team"},
                "standings": [
                    {
                        "rank": 1, "roster_id": 1, "owner_id": "u1",
                        "username": "Alice", "team_name": "A Team", "wins": 1,
                        "losses": 0, "ties": 0, "fpts": 120.0,
                        "fpts_against": 80.0, "playoff_finish": 1,
                    },
                    {
                        "rank": 2, "roster_id": 2, "owner_id": "u2",
                        "username": "Bob", "team_name": "B Team", "wins": 0,
                        "losses": 1, "ties": 0, "fpts": 80.0,
                        "fpts_against": 120.0, "playoff_finish": 2,
                    },
                ],
                "matchups": [{
                    "season": "2025", "week": 1, "is_playoff": False,
                    "rid_a": "1", "rid_b": "2", "score_a": 120.0, "score_b": 80.0,
                }],
                "draft_picks": [{
                    "pick_no": 1, "round": 1, "pick_in_round": 1, "draft_slot": 1,
                    "picked_by": "u1", "player_id": "p1",
                    "metadata": {
                        "first_name": "Draft", "last_name": "Hit", "position": "QB",
                    },
                }],
                "roster_entries": [
                    {
                        "season": "2025", "week": week, "roster_id": 1,
                        "matchup_id": 1,
                        "players": ["p1", "p3"] + (["p5"] if week <= 2 else ["p4"]),
                        "starters": ["p1"] + (["p4"] if week >= 3 else []),
                        "players_points": (
                            {"p1": 10, "p3": 8, "p4": 15} if week >= 3
                            else {"p1": 10, "p3": 8, "p5": 4}
                        ),
                    }
                    for week in (1, 2, 3, 4)
                ] + [
                    {
                        "season": "2025", "week": week, "roster_id": 2,
                        "matchup_id": 1,
                        "players": ["p4"] if week <= 2 else ["p5"],
                        "starters": ["p4"] if week <= 2 else ["p5"],
                        "players_points": {"p4": 5} if week <= 2 else {"p5": 7},
                    }
                    for week in (1, 2, 3, 4)
                ],
                "league_settings": {
                    "total_rosters": 2, "roster_positions": [],
                    "scoring_settings": {}, "waiver_type": 2, "waiver_budget": 100,
                },
            },
        },
    }
    harness = tmp_path / "league_history_loaded.py"
    harness.write_text(
        f"import sys\nsys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import page_league_history as p\n"
        "p._OFFLINE = False\n"
        f"p._fetch_sleeper_history = lambda _league_id, max_seasons=None: {fixture!r}\n"
        "p._league_history_chain = lambda _league_id: ["
        "{'league_id': '1255197436951932928', 'season': '2025', 'name': 'Test League'}"
        "]\n"
        f"p._fetch_one_season = lambda _league_id: ('2025', {fixture['seasons']['2025']!r})\n"
        "p._fetch_season_transactions = lambda _league_id: ["
        "{'type': 'waiver', 'status': 'complete', 'leg': 2, "
        "'settings': {'waiver_bid': 1}, 'adds': {'p3': 1}}, "
        "{'type': 'waiver', 'status': 'complete', 'leg': 4, "
        "'settings': {'waiver_bid': 18}, 'adds': {'p1': 1}}, "
        "{'type': 'waiver', 'status': 'complete', 'leg': 3, "
        "'settings': {'waiver_bid': 22}, 'adds': {'p99': 1}}, "
        "{'type': 'trade', 'status': 'complete', 'leg': 2, "
        "'transaction_id': 't1', 'roster_ids': [1, 2], "
        "'adds': {'p4': 1, 'p5': 2}, 'drops': {'p4': 2, 'p5': 1}}"
        "]\n"
        "p._fetch_player_directory = lambda: {}\n"
        "p.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    league_input = next(widget for widget in at.text_input if widget.key == "lh_league_id")
    league_input.set_value("1255197436951932928")
    next(button for button in at.button if button.label == "Load league history").click()
    at.run()

    assert not at.exception, at.exception
    assert [tab.label for tab in at.tabs][:2] == [
        "🧠 Draft & Roster Insights", "🏆 All-Time Leaderboard",
    ]
    insight_window = next(widget for widget in at.radio if widget.key == "lh_insight_window")
    assert list(insight_window.options) == [
        "Last season", "Last 3 seasons", "All available seasons",
    ]
    assert insight_window.value == "Last 3 seasons"
    insight_view = next(
        widget for widget in at.segmented_control if widget.key == "lh_insight_segment"
    )
    assert list(insight_view.options) == ["My Team", "Best Values", "Draft Room"]
    assert insight_view.value == "My Team"
    md = " ".join(str(m.value) for m in at.markdown)
    assert "st-key-lh_insight_segment" in md
    insight_view.set_value("Best Values")
    at.run()
    assert not at.exception, at.exception
    assert not any(button.label == "Load acquisition history" for button in at.button)
    assert any("cluster at $0" in str(caption.value) for caption in at.caption)
    assert any("four rostered weeks" in str(caption.value) for caption in at.caption)
    assert any("No roster-week minimum" in str(caption.value) for caption in at.caption)
    assert any("sit beside cheap claims" in str(caption.value) for caption in at.caption)
    assert any("never scored in a starting lineup" in str(caption.value) for caption in at.caption)
    assert any("week after the trade" in str(caption.value) for caption in at.caption)
    assert not any(
        "Production acquired after the draft" in str(caption.value)
        for caption in at.caption
    )
    insight_view = next(
        widget for widget in at.segmented_control if widget.key == "lh_insight_segment"
    )
    insight_view.set_value("Draft Room")
    at.run()
    assert not at.exception, at.exception
    assert any(tab.label == "⚔️ Rivalries" for tab in at.tabs)
    assert len(at.get("plotly_chart")) >= 4
    _lb_labels = [metric.label for metric in at.metric]
    _card_order = [
        "Most Titles",
        "Most Finals Appearances",
        "Longest Active Playoff Streak",
        "Best Win %",
        "Most Points",
        "Most Toilet Bowl Titles",
        "Most Toilet Bracket Finals Appearances",
        "Lowest Scoring Team",
    ]
    _card_idx = [_lb_labels.index(label) for label in _card_order]
    assert _card_idx == list(range(_card_idx[0], _card_idx[0] + 8))
    _finals = next(metric for metric in at.metric if metric.label == "Most Finals Appearances")
    assert _finals.value == "Alice\nBob"
    assert not any(metric.label == "Most Finals" for metric in at.metric)
    assert not any(metric.label == "Best Adjusted Scorer" for metric in at.metric)
    assert not any(metric.label == "Most Seasons" for metric in at.metric)
    for _lb_label, _lb_help in page_league_history._LEADERBOARD_METRIC_HELP.items():
        _lb_metric = next(metric for metric in at.metric if metric.label == _lb_label)
        assert _lb_metric.help == _lb_help
    assert not any(
        "does not break a title tie" in str(caption.value) for caption in at.caption
    )
    assert any(metric.label == "🍀 Luckiest Win (All-Play)" for metric in at.metric)
    for _hof_label, _hof_help in page_league_history._HOF_METRIC_HELP.items():
        _hof_metric = next(metric for metric in at.metric if metric.label == _hof_label)
        assert _hof_metric.help == _hof_help
    _hof_order = list(page_league_history._HOF_METRIC_HELP)
    _metric_labels = [metric.label for metric in at.metric]
    _hof_start = _metric_labels.index(_hof_order[0])
    assert _metric_labels[_hof_start:_hof_start + 8] == _hof_order
    assert not any("More Records" in str(item.value) for item in at.markdown)
    assert not any("Scoring Range" in str(item.value) for item in at.markdown)
    assert not any("widest scoring spread" in str(item.value) for item in at.markdown)
    assert any(
        "came in a year whose league average was" in str(caption.value)
        for caption in at.caption
    )
    painful = next(metric for metric in at.metric if metric.label == "😤 Most Painful Loss")
    assert painful.delta == "Alice def. Bob · 2025 Wk 1 (120 - 80)"
    assert not any("lost by" in str(metric.delta) for metric in at.metric)
    assert any(metric.label == "Scoring vs League" for metric in at.metric)
    assert any(
        "All-time is scoring versus the league, season by season" in str(caption.value)
        for caption in at.caption
    )
    assert any(
        "Flip to one season and it goes weekly" in str(caption.value)
        for caption in at.caption
    )
    assert any(metric.label == "Most Consistent" for metric in at.metric)
    for _cl_label, _cl_help in page_league_history._CONSISTENCY_LUCK_METRIC_HELP.items():
        _cl_metric = next(metric for metric in at.metric if metric.label == _cl_label)
        assert _cl_metric.help == _cl_help
    _cl_order = list(page_league_history._CONSISTENCY_LUCK_METRIC_HELP)
    _metric_labels = [metric.label for metric in at.metric]
    _cl_start = _metric_labels.index(_cl_order[0])
    assert _metric_labels[_cl_start:_cl_start + 4] == _cl_order
    md = " ".join(str(m.value) for m in at.markdown)
    assert "upper-right area is the ideal" in md
    assert "lower-right area is the ideal" not in md
    consistency_card = next(
        metric for metric in at.metric if metric.label == "Consistency"
    )
    assert "SD" not in str(consistency_card.value)
    assert str(consistency_card.value).startswith("±")
    assert "pts" in str(consistency_card.value)
    assert "own average" in str(consistency_card.help)
    assert any(expander.label == "View complete manager records" for expander in at.expander)
    rivalry_view = next(widget for widget in at.radio if widget.key == "lh_rivalry_view")
    assert rivalry_view.value == "Build a Week"
    assert {"lh_rivalry_mode", "lh_rivalry_history"} <= {
        widget.key for widget in at.selectbox
    }
    assert not {"lh_h2h_manager_a", "lh_h2h_manager_b"} & {
        widget.key for widget in at.selectbox
    }
    assert not any(
        button.label == "Generate another slate" for button in at.button
    )
    assert not any(
        "Lock matchups" in str(getattr(widget, "label", ""))
        for widget in at.multiselect
    )
    md = " ".join(str(m.value) for m in at.markdown)
    assert "jsa-lh-mode" not in md
    assert any(
        "Classic Rivalries: longest series" in str(caption.value)
        for caption in at.caption
    )
    assert any(
        "historical fit, not a prediction" in str(caption.value)
        for caption in at.caption
    )
    assert any(
        "Classic Rivalries mostly rewards long series" in str(caption.value)
        for caption in at.caption
    )
    assert "RIVALRY SCORE" in md
    assert "70+ fit" in md
    assert not any(
        expander.label == "View complete head-to-head record matrix"
        for expander in at.expander
    )

    rivalry_view.set_value("Explore a Matchup")
    at.run()
    assert not at.exception, at.exception
    assert {"lh_h2h_manager_a", "lh_h2h_manager_b"} <= {
        widget.key for widget in at.selectbox
    }
    assert not {"lh_rivalry_mode", "lh_rivalry_history"} & {
        widget.key for widget in at.selectbox
    }
    alice_average = next(
        metric for metric in at.metric if metric.label == "Alice Avg Score"
    )
    bob_average = next(
        metric for metric in at.metric if metric.label == "Bob Avg Score"
    )
    assert alice_average.value == "120.0 pts"
    assert bob_average.value == "80.0 pts"

    next(
        widget for widget in at.radio if widget.key == "lh_rivalry_view"
    ).set_value("League Matrix")
    at.run()
    assert not at.exception, at.exception
    assert any(
        expander.label == "View complete head-to-head record matrix"
        for expander in at.expander
    )
    assert not {"lh_h2h_manager_a", "lh_h2h_manager_b"} & {
        widget.key for widget in at.selectbox
    }
    assert any(
        expander.label == "View complete career season history"
        for expander in at.expander
    )
    assert any(
        expander.label == "View complete opponent breakdown"
        for expander in at.expander
    )
    md = " ".join(str(m.value) for m in at.markdown)
    assert "Meeting count on the bar is the sample size" in md
    assert "true opponent-specific scoring edge" not in md
    assert "most favorable scoring matchup" not in md
    assert any(
        expander.label == "View complete consistency and luck metrics"
        for expander in at.expander
    )
    assert not any(tab.label == "📈 Score Trends" for tab in at.tabs)
    assert not any(
        expander.label == "View complete score trend data"
        for expander in at.expander
    )
    assert not any(metric.label == "League Average" for metric in at.metric)
    assert not any(metric.label == "Biggest Riser" for metric in at.metric)

    season_filter = next(
        widget for widget in at.selectbox if widget.key == "lh_season_filter"
    )
    season_filter.set_value("2025")
    at.run()
    assert not at.exception, at.exception
    assert any(metric.label == "Scoring vs League" for metric in at.metric)
    assert not any(metric.label == "League Average" for metric in at.metric)


def test_player_history_uses_four_week_filter_and_excludes_null_matchup_points():
    entries = []
    for week, matchup_id in ((1, 1), (2, 2), (3, 3), (18, None)):
        entries.append({
            "season": "2025", "week": week, "roster_id": 4, "matchup_id": matchup_id,
            "players": ["p1", "p2", "p3"] if week <= 3 else ["p1", "p3"],
            "starters": ["p1", "p3"] if week <= 2 else ["p3"],
            "players_points": {
                "p1": {1: 10, 2: 20, 3: 30, 18: 99}[week],
                "p2": 4,
                "p3": 5,
            },
        })
    seasons = {
        "2025": {
            "draft_id": "draft-2025",
            "standings": [{"roster_id": 4, "owner_id": "u1", "username": "Manager"}],
            "draft_picks": [{
                "pick_no": 88, "round": 8, "pick_in_round": 4, "draft_slot": 4,
                "picked_by": "u1", "player_id": "p1",
                "metadata": {"first_name": "Draft", "last_name": "Hit", "position": "QB"},
            }],
            "roster_entries": entries,
        }
    }
    directory = {
        "p1": {"full_name": "Draft Hit", "position": "QB"},
        "p2": {"full_name": "Short Stay", "position": "WR"},
        "p3": {"full_name": "Added Player", "position": "RB"},
    }

    weeks = league_intel.player_week_frame(seasons, directory)
    summary = league_intel.player_season_summary(weeks, min_roster_weeks=4)
    assert set(summary["player_id"]) == {"p1", "p3"}

    p1 = summary.set_index("player_id").loc["p1"]
    assert p1["roster_weeks"] == 4
    assert p1["starts"] == 2
    assert p1["lineup_points"] == 30
    assert p1["roster_points"] == 60
    assert p1["bench_points"] == 30

    values = league_intel.value_frame(summary, league_intel.draft_pick_frame(seasons))
    sources = values.set_index("player_id")["source"].to_dict()
    assert sources == {"p1": "Drafted", "p3": "In-season addition"}
    chart, max_round = league_intel.production_chart_frame(values)
    lanes = chart.set_index("player_id")["lane"].to_dict()
    assert lanes == {"p1": "Drafted", "p3": "Pickup"}
    assert max_round == 8
    assert float(chart.set_index("player_id").loc["p3", "chart_x"]) == max_round + 1


def test_insight_window_includes_last_season():
    completed = ["2022", "2023", "2024", "2025"]
    all_seasons = completed + ["2026"]
    assert league_intel.select_insight_seasons(
        all_seasons, completed, "Last season",
    ) == ["2025"]
    assert league_intel.select_insight_seasons(
        all_seasons, completed, "Last 3 seasons",
    ) == ["2023", "2024", "2025"]
    assert league_intel.select_insight_seasons(
        all_seasons, completed, "All available seasons",
    ) == all_seasons
    assert league_intel.DEFAULT_INSIGHT_WINDOW == "Last 3 seasons"


def test_transaction_adds_keep_first_faab_and_ignore_failed_claims():
    transactions = [
        {
            "type": "waiver", "status": "failed", "leg": 1,
            "settings": {"waiver_bid": 40},
            "adds": {"p3": 4},
        },
        {
            "type": "waiver", "status": "complete", "leg": 2,
            "settings": {"waiver_bid": 17},
            "adds": {"p3": 4},
        },
        {
            "type": "free_agent", "status": "complete", "leg": 6,
            "settings": None, "adds": {"p4": 4},
        },
        {
            "type": "trade", "status": "complete", "leg": 8,
            "adds": {"p5": 4}, "waiver_budget": [{"sender": 4, "receiver": 1, "amount": 5}],
        },
        {
            "type": "waiver", "status": "complete", "leg": 3,
            "settings": {"waiver_bid": 3},
            "adds": {"p3": 4},
        },
    ]
    owner = {("2025", "4"): "u1"}
    acquired = league_intel.first_acquisition_frame({"2025": transactions}, owner)
    by_player = acquired.set_index("player_id")
    assert by_player.loc["p3", "source"] == "Waiver"
    assert int(by_player.loc["p3", "faab"]) == 17
    assert int(by_player.loc["p3", "week"]) == 2
    assert by_player.loc["p4", "source"] == "Free agent"
    assert int(by_player.loc["p4", "faab"]) == 0
    assert by_player.loc["p5", "source"] == "Trade"
    assert pd.isna(by_player.loc["p5", "faab"])

    values = pd.DataFrame([
        {"season": "2025", "user_id": "u1", "player_id": "p3",
         "player_name": "Added Player", "position": "RB", "lineup_points": 80,
         "starts": 8, "source": "In-season addition", "round": pd.NA, "pick_no": pd.NA},
        {"season": "2025", "user_id": "u1", "player_id": "p1",
         "player_name": "Draft Hit", "position": "QB", "lineup_points": 30,
         "starts": 2, "source": "Drafted", "round": 8, "pick_no": 88},
    ])
    labeled = league_intel.attach_acquisitions(values, acquired)
    assert labeled.set_index("player_id").loc["p3", "source"] == "Waiver"
    assert labeled.set_index("player_id").loc["p1", "source"] == "Drafted"
    cheap, paid = league_intel.split_faab_waiver_frames(labeled)
    assert list(cheap["player_id"]) == []
    assert list(paid["player_id"]) == ["p3"]
    cheap_one, paid_one = league_intel.split_faab_waiver_frames(pd.DataFrame([
        {"source": "Waiver", "faab": 1, "player_id": "cheap", "lineup_points": 40},
        {"source": "Waiver", "faab": 12, "player_id": "paid", "lineup_points": 90},
        {"source": "Free agent", "faab": 0, "player_id": "fa", "lineup_points": 70},
    ]))
    assert list(cheap_one["player_id"]) == ["cheap"]
    assert list(paid_one["player_id"]) == ["paid"]
    assert league_intel.league_uses_faab({
        "2025": {"league_settings": {"waiver_type": 2, "waiver_budget": 100}},
    })
    assert not league_intel.league_uses_faab({
        "2025": {"league_settings": {"waiver_type": 0}},
    })


def test_trade_outcome_scores_got_versus_gave_from_week_after():
    transactions = [
        {
            "type": "trade", "status": "complete", "leg": 2,
            "transaction_id": "t1", "roster_ids": [1, 2],
            "adds": {"got1": 1, "gave1": 2},
            "drops": {"got1": 2, "gave1": 1},
            "draft_picks": [{
                "season": "2026", "round": 2,
                "owner_id": 1, "previous_owner_id": 2,
            }],
            "waiver_budget": [{"sender": 1, "receiver": 2, "amount": 5}],
        },
        {
            "type": "trade", "status": "failed", "leg": 3,
            "transaction_id": "t_fail", "roster_ids": [1, 2],
            "adds": {"x": 1}, "drops": {"x": 2},
        },
        {
            "type": "waiver", "status": "complete", "leg": 4,
            "adds": {"waived": 1},
        },
        {
            "type": "trade", "status": "complete", "leg": 10,
            "transaction_id": "t_picks", "roster_ids": [1, 2],
            "adds": {}, "drops": {},
            "draft_picks": [{
                "season": "2026", "round": 3,
                "owner_id": 2, "previous_owner_id": 1,
            }],
        },
    ]
    owner = {("2025", "1"): "u1", ("2025", "2"): "u2"}
    weeks = pd.DataFrame([
        {
            "season": "2025", "week": 2, "user_id": "u1", "roster_id": "1",
            "player_id": "got1", "player_name": "Incoming", "position": "WR",
            "is_starter": True, "active_matchup": True, "points": 99.0,
        },
        {
            "season": "2025", "week": 3, "user_id": "u1", "roster_id": "1",
            "player_id": "got1", "player_name": "Incoming", "position": "WR",
            "is_starter": True, "active_matchup": True, "points": 10.0,
        },
        {
            "season": "2025", "week": 4, "user_id": "u1", "roster_id": "1",
            "player_id": "got1", "player_name": "Incoming", "position": "WR",
            "is_starter": True, "active_matchup": True, "points": 12.0,
        },
        {
            "season": "2025", "week": 3, "user_id": "u2", "roster_id": "2",
            "player_id": "gave1", "player_name": "Outgoing", "position": "RB",
            "is_starter": True, "active_matchup": True, "points": 6.0,
        },
        {
            "season": "2025", "week": 4, "user_id": "u2", "roster_id": "2",
            "player_id": "gave1", "player_name": "Outgoing", "position": "RB",
            "is_starter": True, "active_matchup": True, "points": 7.0,
        },
        {
            "season": "2025", "week": 3, "user_id": "u2", "roster_id": "2",
            "player_id": "gave1", "player_name": "Outgoing", "position": "RB",
            "is_starter": False, "active_matchup": True, "points": 50.0,
        },
    ])
    out = league_intel.trade_outcome_frame(
        {"2025": transactions}, owner, weeks, "u1",
        {"u1": "Alice", "u2": "Bob"},
    )
    assert list(out["transaction_id"]) == ["t1"]
    row = out.iloc[0]
    assert row["got_points"] == 22.0
    assert row["gave_points"] == 13.0
    assert row["net"] == 9.0
    assert row["got_names"] == "Incoming"
    assert row["gave_names"] == "Outgoing"
    assert "got 2026 R2" in row["extra"]
    assert "sent $5 FAAB" in row["extra"]
    assert row["opponent"] == "Bob"
    assert not bool(row["player_only"])
    empty = league_intel.trade_outcome_frame(
        {"2025": transactions}, owner, weeks, "u3", {},
    )
    assert empty.empty


def test_paid_waiver_claims_ignore_roster_week_floor():
    transactions = [
        {
            "type": "waiver", "status": "complete", "leg": 8,
            "settings": {"waiver_bid": 22},
            "adds": {"short": 1},
        },
        {
            "type": "waiver", "status": "complete", "leg": 2,
            "settings": {"waiver_bid": 1},
            "adds": {"cheap": 1},
        },
        {
            "type": "waiver", "status": "failed", "leg": 3,
            "settings": {"waiver_bid": 40},
            "adds": {"missed": 1},
        },
        {
            "type": "waiver", "status": "complete", "leg": 4,
            "settings": {"waiver_bid": 12},
            "adds": {"ghost": 1},
        },
        {
            "type": "waiver", "status": "complete", "leg": 9,
            "settings": {"waiver_bid": 30},
            "adds": {"short": 1},
        },
    ]
    owner = {("2025", "1"): "u1"}
    weeks = pd.DataFrame([
        {
            "season": "2025", "week": 8, "user_id": "u1", "roster_id": "1",
            "player_id": "short", "player_name": "One Week", "position": "WR",
            "is_starter": True, "active_matchup": True, "points": 14.0,
        },
        {
            "season": "2025", "week": 2, "user_id": "u1", "roster_id": "1",
            "player_id": "cheap", "player_name": "Streamer", "position": "RB",
            "is_starter": True, "active_matchup": True, "points": 9.0,
        },
    ])
    paid = league_intel.paid_waiver_claim_frame(
        {"2025": transactions}, owner, weeks, "u1",
    )
    by_player = paid.set_index("player_id")
    assert set(by_player.index) == {"short", "ghost"}
    assert int(by_player.loc["short", "faab"]) == 30
    assert by_player.loc["short", "lineup_points"] == 14.0
    assert by_player.loc["ghost", "lineup_points"] == 0.0
    assert by_player.loc["ghost", "player_name"] == "ghost"
    producers, busts = league_intel.split_paid_production_frames(paid)
    assert list(producers["player_id"]) == ["short"]
    assert list(busts["player_id"]) == ["ghost"]


def test_trade_chart_caps_to_most_lopsided():
    rows = []
    for i in range(10):
        rows.append({
            "season": "2025", "week": i + 1, "transaction_id": f"t{i}",
            "user_id": "u1", "got_points": float(i), "gave_points": 4.0,
            "net": float(i) - 4.0, "got_names": f"Got{i}",
            "gave_names": f"Gave{i}", "extra": "", "opponent": "Bob",
            "label": f"2025 W{i + 1} vs Bob", "player_only": True,
        })
    trades = pd.DataFrame(rows)
    shown = league_intel.select_trade_chart_rows(trades, limit=8)
    assert list(shown["transaction_id"]) == [
        "t0", "t1", "t2", "t3", "t6", "t7", "t8", "t9",
    ]
    small = league_intel.select_trade_chart_rows(trades.head(3), limit=8)
    assert list(small["transaction_id"]) == ["t0", "t1", "t2"]
    assert league_intel.compact_name_list("A, B, C, D") == "A, B +2"
    labels = league_intel.trade_opponent_labels(pd.DataFrame([
        {"opponent": "Bob", "season": "2025", "week": 3},
        {"opponent": "Bob", "season": "2025", "week": 8},
    ]))
    assert labels == ["Bob · 2025 W3", "Bob · 2025 W8"]


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        test_weekly_fantasy_renders_and_owns_controls(p)
        test_league_history_renders_and_lands_empty(p)
    print("OK  WF owns wf_* controls; LH lands empty with the resting prompt")
