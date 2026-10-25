import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from publishing.cbb_daily import (
    CARD_COLUMNS,
    CARD_SCHEMA_VERSION,
    OPTIONAL_CARD_COLUMNS,
    RESULT_COLUMNS,
    publish_card_candidate,
    publish_result_candidate,
)
from publishing.contract import sha256_file


ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")
DAY = date(2026, 11, 2)
HASHES = {
    "model_hash": "f83da7ac2015f8c23dfa41d52d5a2b1325ec0a7cad3e3b03e53bc2c957d27800",
    "feature_hash": "c08adcfed32f497bf98dbea61b203bb2df5d5a5b0554f02b135cd7b3eb1bf89f",
    "policy_hash": "79f5b87a552e2fbfd72e0578e500a1525cd492542e39d04850cb40da1d60a66d",
}
BENCHMARK_HASH = "7b038b0e82196fe88d5bd4c57b5834f7c7d3f3d3df5d50a31f5c7ac4284b2930"
NOTICE = "No official sportsbook line snapshot for this date, so no ATS plays are shown."
PRESEASON = {"poll": "AP Top 25", "poll_date": "2026-10-20", "week": 1, "source": "static_snapshot"}
WEEKLY = {"poll": "AP Top 25", "poll_date": "2026-11-09", "week": 3, "source": "cbbd"}
BADGE = ":orange-badge[8.5+ gap, exploratory]"

# team -> (CBBD conference short name, AP rank or None). Two teams share #25 because ties are legal.
TEAMS = {
    "Kansas": ("Big 12", None), "Duke": ("ACC", 2), "UCLA": ("Big Ten", None), "Oregon": ("Big Ten", None),
    "Michigan State": ("Big Ten", 14), "Wisconsin": ("Big Ten", 25), "Miami (OH)": ("MAC", None), "Ohio": ("MAC", None),
    "Gonzaga": ("WCC", 11), "Saint Mary's (CA)": ("WCC", 25), "Southeast Missouri State": ("OVC", None),
    "Texas A&M-Corpus Christi": ("Southland", None),
}

# home, away, predicted home margin, predicted total, home spread (None = no line), tip hour ET, neutral
GAMES = [
    ("Kansas", "Duke", 4.20, 148.4, -3.25, 12.0, False),
    ("UCLA", "Oregon", 11.96, 141.2, -3.5, 14.0, False),
    ("Michigan State", "Wisconsin", 14.0, 139.6, -3.0, 16.0, False),
    ("Miami (OH)", "Ohio", -9.4, 146.8, -0.25, 17.0, False),
    ("Gonzaga", "Saint Mary's (CA)", 1.5, 137.0, 0.0, 19.0, True),
    ("Southeast Missouri State", "Texas A&M-Corpus Christi", -6.3, 141.8, None, 20.0, False),
]


def _utc(hour: float, day: date = DAY) -> str:
    local = datetime(day.year, day.month, day.day, int(hour), int(round((hour % 1) * 60)), tzinfo=ET)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(index: int, game: tuple, *, lines: bool, day: date = DAY) -> dict:
    home, away, margin, total, spread, tip, neutral = game
    home_score, away_score = (total + margin) / 2, (total - margin) / 2
    row = {column: "" for column in CARD_COLUMNS + OPTIONAL_CARD_COLUMNS}
    (home_conference, home_rank), (away_conference, away_rank) = TEAMS.get(home, ("", None)), TEAMS.get(away, ("", None))
    row.update({
        "home_conference": home_conference, "away_conference": away_conference,
        "home_rank": home_rank or "", "away_rank": away_rank or "",
        "game_id": f"{day:%Y%m%d}{index:03d}", "season": 2027, "game_date_et": day.isoformat(), "tipoff_utc": _utc(tip, day),
        "home_team_id": f"h{index}", "home_team": home, "away_team_id": f"a{index}", "away_team": away,
        "neutral_site": neutral, "conference_game": True,
        "predicted_home_score": round(home_score, 4), "predicted_away_score": round(away_score, 4),
        "predicted_margin": round(home_score, 4) - round(away_score, 4), "predicted_total": round(home_score, 4) + round(away_score, 4),
        "predicted_winner": "home" if margin > 0 else "away", "home_win_probability": round(1 / (1 + math.exp(-0.18 * margin)), 6),
        "prediction_at_utc": _utc(8.3333, day), "prediction_run_hash": "pred", **HASHES,
    })
    if lines and spread is not None:
        edge = row["predicted_margin"] + spread
        pick = "home" if edge >= 8.5 else ("away" if edge <= -8.5 else "no_play_below_threshold")
        row.update({
            "market_home_spread": spread, "market_home_margin": -spread, "provider_count": 5, "market_status": "available",
            "model_edge": edge, "ats_pick": pick, "ats_status": "candidate" if pick in {"home", "away"} else "no_play",
            "line_retrieved_at_utc": _utc(8.9167, day), "decision_time_utc": _utc(8.9167, day), "ats_card_run_hash": "ats",
        })
    else:
        row.update({
            "market_home_spread": "", "market_home_margin": "", "provider_count": 0, "market_status": "missing_line",
            "model_edge": "", "ats_pick": "no_play_line_unavailable", "ats_status": "line_unavailable",
            "line_retrieved_at_utc": "", "decision_time_utc": "", "ats_card_run_hash": "",
        })
    return row


def _publish_card(root: Path, *, lines: bool, games=GAMES, day: date = DAY, status: str | None = None, name: str = "card.csv", coverage: dict | None = None,
                  top25: dict | None = PRESEASON, extras: bool = True) -> dict:
    """Publish a card. ``extras=False`` writes the older card shape: no conference or rank columns, no ``top25``."""
    rows = [_row(i + 1, game, lines=lines, day=day) for i, game in enumerate(games)]
    if status is None:
        status = "official" if any(r["market_status"] == "available" for r in rows) else "unavailable"
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / f"{day.isoformat()}-{name}"
    pd.DataFrame(rows, columns=CARD_COLUMNS + (OPTIONAL_CARD_COLUMNS if extras else ())).to_csv(artifact, index=False, lineterminator="\n")
    metadata = {
        "schema_version": CARD_SCHEMA_VERSION, "product": "cbb_daily_spreads", "season": 2027, "game_date_et": day.isoformat(),
        "status": "published" if rows else "no_games_scheduled", "artifact_sha256": sha256_file(artifact), "expected_rows": len(rows),
        "expected_game_ids": [r["game_id"] for r in rows], "historical_benchmark_hash": BENCHMARK_HASH, "threshold": 8.5,
        "prediction_run_hash": "pred", "line_snapshot_status": status, "prediction_at_utc": _utc(8.3333, day),
        "attribution": "Data provided by CollegeBasketballData.com", **HASHES,
    }
    if extras:
        metadata["top25"] = top25
    if coverage is not None:
        metadata["coverage"] = coverage
    return publish_card_candidate(artifact, metadata, root=root)


def _publish_results(root: Path, entry: dict, outcomes: dict[int, tuple[int, int] | None], *, day: date = DAY) -> None:
    """outcomes: game index (1-based) -> (home_score, away_score), or None for a game not final yet."""
    card = pd.read_csv(root / entry["artifact"], dtype={"game_id": "string"}).set_index("game_id", drop=False)
    rows = []
    for index, outcome in outcomes.items():
        source = card.loc[f"{day:%Y%m%d}{index:03d}"]
        if outcome is None:
            rows.append({"game_id": source["game_id"], "game_date_et": day.isoformat(), "home_score": "", "away_score": "", "actual_home_margin": "",
                         "actual_cover_margin": "", "ats_result": "ungraded", "finalized_at_utc": "", "source_card_build_id": entry["build_id"]})
            continue
        home, away = outcome
        margin = home - away
        market_margin = source["market_home_margin"]
        cover = margin - float(market_margin) if pd.notna(market_margin) else ""
        pick = str(source["ats_pick"])
        if pick in {"home", "away"}:
            result = "push" if cover == 0 else ("win" if (pick == "home") == (cover > 0) else "loss")
        else:
            result = "no_play"
        rows.append({"game_id": source["game_id"], "game_date_et": day.isoformat(), "home_score": home, "away_score": away, "actual_home_margin": margin,
                     "actual_cover_margin": cover, "ats_result": result, "finalized_at_utc": _utc(2.5, day + timedelta(days=1)),
                     "source_card_build_id": entry["build_id"]})
    artifact = root / f"{day.isoformat()}-results.csv"
    pd.DataFrame(rows, columns=RESULT_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    metadata = {
        "schema_version": "cbb_daily_results_v1", "product": "cbb_daily_spreads_results", "season": 2027, "game_date_et": day.isoformat(),
        "source_card_build_id": entry["build_id"], "source_card_sha256": entry["sha256"], "artifact_sha256": sha256_file(artifact),
        "expected_rows": len(rows), "status": "graded", **HASHES,
    }
    publish_result_candidate(artifact, metadata, root=root)


@pytest.fixture
def render(tmp_path, monkeypatch):
    """Render page_cbb_daily against a fixture release root and hand back the AppTest."""
    import cbb_daily_data

    monkeypatch.setenv("APP_OFFLINE", "1")
    loaders = (cbb_daily_data.load_manifest, cbb_daily_data.load_card, cbb_daily_data.load_results, cbb_daily_data.load_conference_order)
    harness = tmp_path / "harness.py"
    harness.write_text(
        f"import sys; sys.path[:0]=[r'{ROOT}', r'{ROOT / 'site_pages'}']\n"
        "import page_cbb_daily; page_cbb_daily.render()\n",
        encoding="utf-8",
    )

    def _render(root: Path | None = None, *, today: date | None = DAY, select: str | None = None, view: str | None = None, search: str | None = None) -> AppTest:
        for loader in loaders:
            loader.clear()
        monkeypatch.setenv("JSA_CBB_FIXTURE_DIR", str(root or tmp_path))
        import page_cbb_daily

        if today is not None:
            class _Clock(datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime(today.year, today.month, today.day, 12, 0, tzinfo=tz)

            monkeypatch.setattr(page_cbb_daily, "datetime", _Clock)
        at = AppTest.from_file(str(harness), default_timeout=180).run()
        if select:
            at.selectbox(key="cbb_card_date").set_value(select).run()
        if view is not None:
            at.selectbox(key="cbb_view").set_value(view).run()
        if search is not None:
            at.text_input(key="cbb_team_search").set_value(search).run()
        assert not at.exception, at.exception
        return at

    yield _render
    for loader in loaders:
        loader.clear()


def _all_text(at: AppTest) -> str:
    parts: list[str] = []
    for kind in ("title", "header", "subheader", "markdown", "caption", "info", "warning", "success", "error"):
        parts += [str(element.value) for element in getattr(at, kind)]
    parts += [f"{metric.label} {metric.value} {metric.delta}" for metric in at.metric]
    for frame in at.dataframe:
        parts.append(frame.value.to_csv(index=False))
    return "\n".join(parts)


def _game_cards(at: AppTest) -> list[str]:
    return [str(m.value) for m in at.markdown if "win probability" in str(m.value)]


def _pick_cards(at: AppTest) -> list[str]:
    return [str(m.value) for m in at.markdown if str(m.value).startswith("**Shadow pick:")]


def _view_menu(at: AppTest) -> list[str]:
    return list(at.selectbox(key="cbb_view").options)


def _view_keys(at: AppTest) -> list[str]:
    return [re.sub(r" \(\d+ games?\)$", "", label) for label in _view_menu(at)]


def _across_views(at: AppTest, collect) -> dict:
    """Run ``collect(at)`` once per entry of the View menu. The menu is the only way to reach a day's games."""
    results = {}
    for view in _view_keys(at):
        at.selectbox(key="cbb_view").set_value(view).run()
        assert not at.exception, at.exception
        results[view] = collect(at)
    return results


def _card_lines(at: AppTest) -> list[str]:
    """The ``Line: ...`` / ``No line yet`` row of every game card on screen, in order."""
    return [str(m.value) for m in at.markdown if str(m.value).startswith(("Line:", "No line yet"))]


def _badges(at: AppTest) -> list[str]:
    return [str(m.value) for m in at.markdown if "gap, exploratory" in str(m.value)]


def _headlines(at: AppTest) -> list[str]:
    """The bold headline of every game card on screen, in order, for example ``Kansas by 4.2``."""
    return [card.split(" · ")[0].strip("*") for card in _game_cards(at)]


def _game_captions(at: AppTest) -> list[str]:
    """The ``Away at Home · 7:00 PM ET`` caption of every game card on screen, in order."""
    return [str(c.value) for c in at.caption if re.search(r" (at|vs) .* · \d+:\d\d [AP]M ET", str(c.value))]


def test_cbb_page_renders_published_card(tmp_path, render):
    rows = [_row(1, ("Home", "Away", 10.0, 150.0, -1.5, 15.0, False), lines=True)]
    assert rows[0]["model_edge"] == 8.5 and rows[0]["ats_pick"] == "home"
    _publish_card(tmp_path, lines=True, games=[("Home", "Away", 10.0, 150.0, -1.5, 15.0, False)])
    at = render()
    assert not at.error, [error.value for error in at.error]
    assert "**Home by 10.0** · 86% win probability" in _game_cards(at)
    assert _pick_cards(at) == ["**Shadow pick: Home -1.5**"]


def test_cbb_page_predictions_only_shows_team_names(tmp_path, render):
    """A card with no sportsbook line still leads with predictions, in team names, and says why there are no ATS plays."""
    # 1) Predictions-only card: no picks, a visible notice, no HOME/AWAY labels anywhere, "No line yet" on every game.
    only = tmp_path / "only"
    _publish_card(only, lines=False)
    at = render(only)
    assert not at.error, [error.value for error in at.error]
    cards_by_view = _across_views(at, _game_cards)
    cards = sorted({card for found in cards_by_view.values() for card in found})
    assert len(cards) == len(GAMES), "every game is reachable through the View menu"
    assert "**Kansas by 4.2** · 68% win probability" in cards
    assert "**Miami (OH) by 9.4**" not in " ".join(cards)
    assert any(card.startswith("**Ohio by 9.4** · 84% win probability") for card in cards)
    assert any(card.startswith("**Texas A&M-Corpus Christi by 6.3**") for card in cards)
    text = "\n".join(_across_views(at, _all_text).values())
    for name in ("Kansas", "Duke", "UCLA", "Oregon", "Michigan State", "Wisconsin", "Gonzaga", "Saint Mary's (CA)"):
        assert name in text
    assert NOTICE in [str(info.value) for info in at.info]
    assert not _pick_cards(at) and not _badges(at) and len(at.expander) == 0
    captions = [str(c.value) for c in at.caption]
    assert "No sportsbook line is available for this date, so games are listed by tip time." in captions
    assert not any(caption.startswith("Games are listed by gap") for caption in captions)
    assert "Shadow pick" not in text and "Line:" not in text
    assert set(line for found in _across_views(at, _card_lines).values() for line in found) == {"No line yet"}
    assert not re.search(r"\b(HOME|AWAY)\b", text)

    # 2) Card with lines: exact spreads, two-decimal gaps, an 8.46 gap is not a play, picks are team names.
    lined = tmp_path / "lined"
    _publish_card(lined, lines=True)
    at = render(lined)
    assert not at.error, [error.value for error in at.error]
    assert NOTICE not in _all_text(at)
    text = "\n".join(_across_views(at, _all_text).values())
    lines = sorted({line for found in _across_views(at, _card_lines).values() for line in found})
    assert "Line: Kansas -3.25 · Gap 0.95 toward Kansas" in lines
    assert "Line: UCLA -3.5 · Gap 8.46 toward UCLA" in lines
    assert "Line: pick'em · Gap 1.50 toward Gonzaga" in lines
    assert "Line: Michigan State -3 · Gap 11.00 toward Michigan State" in lines
    assert "Line: Miami (OH) -0.25 · Gap 9.65 toward Ohio" in lines
    assert lines.count("No line yet") == 1 and len(lines) == len(GAMES)
    assert sorted(_pick_cards(at)) == ["**Shadow pick: Michigan State -3**", "**Shadow pick: Ohio +0.25**"]
    assert "UCLA" not in " ".join(_pick_cards(at))
    assert "+8.50" not in text and "Gap 8.50" not in text
    assert not re.search(r"\b(HOME|AWAY)\b", text)
    assert "ATS plays are shown" not in text and len(at.expander) == 0
    assert "All games on this card" not in text and "model edge" not in text.lower()


def test_rejected_snapshot_notice_names_the_reason(tmp_path, render):
    _publish_card(tmp_path, lines=False, status="rejected")
    infos = [str(info.value) for info in render().info]
    assert any(info.startswith(NOTICE) and "did not pass our checks" in info for info in infos)


def test_card_without_a_line_snapshot_status_never_shows_plays(tmp_path, render):
    """Fail closed: a stored card whose metadata somehow lacks the status is treated as unavailable."""
    entry = _publish_card(tmp_path, lines=True)
    meta_path = tmp_path / entry["metadata"]
    import json

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    del meta["line_snapshot_status"]
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    at = render()
    assert NOTICE in [str(info.value) for info in at.info]
    assert not _pick_cards(at)


def test_game_cards_lead_with_winner_probability_score_and_total(tmp_path, render):
    _publish_card(tmp_path, lines=False)
    at = render()
    first = next(m for m in at.markdown if str(m.value).startswith("**Kansas by 4.2**"))
    assert str(first.value) == "**Kansas by 4.2** · 68% win probability"
    body = str(at.markdown[list(at.markdown).index(first) + 1].value)
    assert body.startswith("Predicted score: Kansas 76.3, Duke 72.1") and "Predicted total: 148.4" in body
    captions = [str(c.value) for c in at.caption]
    assert "#2 Duke at Kansas · 12:00 PM ET" in captions
    assert "#25 Saint Mary's (CA) vs #11 Gonzaga · 7:00 PM ET · Neutral site" in captions
    assert all("Neutral site" not in caption for caption in captions if "Kansas" in caption)


def test_team_search_looks_through_every_game_whatever_the_view(tmp_path, render):
    """A search ignores the View menu: it finds a team that is not in the Top 25 or the selected conference."""
    _publish_card(tmp_path, lines=True)
    at = render(search="duke")
    assert _headlines(at) == ["Kansas by 4.2"]
    # UCLA is not ranked, so the default Top 25 view never lists it, but searching for it does.
    assert at.selectbox(key="cbb_view").value == "Top 25"
    assert not any("UCLA" in headline for headline in _headlines(render()))
    at = render(search="ucla")
    assert _headlines(at) == ["UCLA by 12.0"]
    assert at.selectbox(key="cbb_view").disabled
    notes = [str(c.value) for c in at.caption if str(c.value).startswith("Searching")]
    assert notes == ["Searching all of this date's games. Clear the box to use the View menu again."]
    # The selected view does not matter either.
    assert _headlines(render(view="ACC", search="michigan")) == ["#14 Michigan State by 14.0"]
    # A search that matches games in several views lists each once, in gap order, then the game with no line.
    assert _headlines(render(view="Big Ten", search="a")) == [
        "#14 Michigan State by 14.0", "Ohio by 9.4", "UCLA by 12.0", "#11 Gonzaga by 1.5", "Kansas by 4.2", "Texas A&M-Corpus Christi by 6.3",
    ]
    # Clearing the search brings the view back, and an unmatched search says so.
    at.text_input(key="cbb_team_search").set_value("").run()
    assert not at.selectbox(key="cbb_view").disabled and not [c for c in at.caption if str(c.value).startswith("Searching")]
    at = render(search="no such team")
    assert [str(info.value) for info in at.info if "No games match" in str(info.value)] == ["No games match that search."]
    assert not _game_cards(at)
    # The ATS plays list below is not filtered by the search box.
    assert sorted(_pick_cards(render(search="duke"))) == ["**Shadow pick: Michigan State -3**", "**Shadow pick: Ohio +0.25**"]


def test_season_prediction_record_counts_games_with_and_without_lines(tmp_path, render):
    # A predictions-only day: results are all `no_play`, yet they still count as finished predictions.
    entry = _publish_card(tmp_path, lines=False)
    # Predicted home margins are 4.2, 11.96, 14.0, -9.4; predicted totals 148.4, 141.2, 139.6, 146.8.
    _publish_results(tmp_path, entry, {
        1: (80, 68),    # home by 12: predicted home win, correct. |4.2-12|=7.8, total 148 vs 148.4: 0.4
        2: (60, 70),    # away by 10: predicted home win, missed. |11.96-(-10)|=21.96, total 130 vs 141.2: 11.2
        3: (75, 70),    # home by 5: correct. |14-5|=9, total 145 vs 139.6: 5.4
        4: (65, 75),    # away by 10: predicted away win, correct. |-9.4-(-10)|=0.6, total 140 vs 146.8: 6.8
        5: None,
        6: None,
    })
    at = render(select=DAY.isoformat())
    metrics = {metric.label: (metric.value, metric.delta) for metric in at.metric}
    assert metrics["Finished games"][0] == "4"
    assert metrics["Winner correct"] == ("75.0%", "3 of 4")
    assert metrics["Avg margin miss"][0] == f"{(7.8 + 21.96 + 9 + 0.6) / 4:.2f} pts"
    assert metrics["Avg total miss"][0] == f"{(0.4 + 11.2 + 5.4 + 6.8) / 4:.2f} pts"
    assert metrics["Games finished"][0] == "4 of 6"
    text = _all_text(at)
    assert "Too early to read. Only 4 games have finished" in text
    # The 2026 holdout row is always there as context, with its recorded numbers.
    assert "**2026 holdout** (scored once, 5,752 games): winner correct **71.9%** · avg margin miss **9.33 pts** · avg total miss **13.78 pts**" in text
    # Per-game results on the cards, collected over every view (a game in two views counts once).
    per_view = _across_views(at, lambda page: [str(m.value) for m in page.markdown if str(m.value).startswith("Final:")])
    finals = sorted({final for found in per_view.values() for final in found})
    assert "Final: Kansas 80, Duke 68 · :green[Winner pick correct]" in finals
    assert "Final: Oregon 70, UCLA 60 · :red[Winner pick missed]" in finals
    assert len(finals) == 4
    # No lines, so the ATS record has nothing to count.
    assert "No graded wins/losses yet." in text and NOTICE in text


def test_ats_record_still_counts_wins_losses_and_pushes(tmp_path, render):
    entry = _publish_card(tmp_path, lines=True)
    _publish_results(tmp_path, entry, {
        1: (80, 70), 2: (70, 66), 3: (80, 70),   # Michigan State -3 covers by 7: win
        4: (70, 71),                              # Ohio +0.25 covers: win
        5: (70, 68), 6: None,
    })
    at = render(select=DAY.isoformat())
    text = _all_text(at)
    assert "2 wins · 0 losses · 0 pushes · ATS rate 100.0%" in text
    assert ("Season shadow record", "2-0-0") in [(metric.label, metric.value) for metric in at.metric]
    outcomes = [str(c.value) for c in at.caption if "model gap" in str(c.value) and "result:" in str(c.value)]
    assert any("Wisconsin at Michigan State" in line and line.endswith("result: win") for line in outcomes)


def test_stale_card_warning_and_no_games_day(tmp_path, render):
    _publish_card(tmp_path, lines=False)
    _publish_card(tmp_path, lines=False, games=[], day=date(2026, 11, 3))
    at = render(today=date(2026, 11, 4))
    assert any("Showing the latest official card from 2026-11-03" in str(w.value) for w in at.warning)
    assert any("No D1-vs-D1 games were scheduled for 2026-11-03" in str(s.value) for s in at.success)
    assert not at.error and not _game_cards(at)
    assert "Season prediction record" in [str(s.value) for s in at.subheader]


def test_empty_state_names_the_2026_27_season(tmp_path, render):
    at = render(tmp_path / "nothing-published", today=None)
    assert [str(w.value) for w in at.warning] == ["No official College Basketball daily card has been published yet."]
    captions = " ".join(str(c.value) for c in at.caption)
    assert "2026-27 season" in captions and "2027 season" not in captions
    assert [str(t.value) for t in at.title] == ["College basketball daily predictions"]
    assert "Data provided by CollegeBasketballData.com" in captions
    assert not at.error


def test_page_copy_has_no_em_or_en_dashes_outside_the_frozen_benchmark(tmp_path, render):
    _publish_card(tmp_path, lines=True)
    entry_text = "\n".join(_across_views(render(), _all_text).values())
    frozen = ("2022–2025 OOF", "344–267–0", "87–64–0", "52.34%–60.18%", "49.64%–65.21%")
    cleaned = entry_text
    for piece in frozen:
        cleaned = cleaned.replace(piece, "")
    assert "—" not in cleaned and "–" not in cleaned


def test_historical_benchmark_table_is_unchanged(tmp_path, render):
    _publish_card(tmp_path, lines=False)
    frames = [frame.value for frame in render().dataframe]
    benchmark = next(frame for frame in frames if list(frame.columns) == ["Period", "Record", "Graded", "ATS rate", "Wilson 95%"])
    assert benchmark.to_dict("records") == [
        {"Period": "2022–2025 OOF", "Record": "344–267–0", "Graded": 611, "ATS rate": 0.5630, "Wilson 95%": "52.34%–60.18%"},
        {"Period": "Season 2026", "Record": "87–64–0", "Graded": 151, "ATS rate": 0.5762, "Wilson 95%": "49.64%–65.21%"},
    ]


def test_formatters_never_round_an_edge_or_spread_into_something_else():
    import page_cbb_daily as page

    assert [page._format_spread(v) for v in (-3.25, -3.0, -3.5, 0.0, -0.0, 2.5, 10.0, -10.75, 3.125)] == ["-3.25", "-3", "-3.5", "PK", "PK", "+2.5", "+10", "-10.75", "+3.125"]
    assert page._format_edge(8.46) == "+8.46" and page._format_edge(-8.46) == "-8.46"
    assert page._format_edge(8.5) == "+8.50" and page._format_edge(-8.5) == "-8.50" and page._format_edge(11.0) == "+11.00"
    # 8.496 rounds to 8.50 but is not a play; it must stay under the threshold on screen.
    assert page._format_edge(8.496) == "+8.49" and page._format_edge(-8.499999) == "-8.49"
    assert page._format_edge(3.456) == "+3.46" and page._format_edge(0.004) == "+0.00" and page._format_edge(-0.004) == "+0.00"
    assert page._format_probability(0.7349) == "73%" and page._format_probability(0.735) == "74%"
    assert page._format_probability(0.9951) == ">99%" and page._format_probability(0.5) == "50%"
    assert page._flag(True) and page._flag("True") and not page._flag(False) and not page._flag(float("nan")) and not page._flag(None) and not page._flag("")
    assert page._md("A_B *C* [D] $E") == "A\\_B \\*C\\* \\[D\\] \\$E"


def test_prediction_summary_matches_a_hand_computation():
    import page_cbb_daily as page

    frame = pd.DataFrame({
        "predicted_margin": [10.0, -5.0, 3.0, 8.0], "actual_home_margin": [12.0, 4.0, -2.0, 6.0],
        "predicted_total": [150.0, 140.0, 160.0, 145.0], "home_score": [82.0, 67.0, 80.0, 73.0], "away_score": [70.0, 63.0, 82.0, 67.0],
    })
    summary = page._prediction_summary(frame)
    assert summary["games"] == 4 and summary["correct"] == 2 and summary["winner_rate"] == 0.5
    assert summary["margin_mae"] == pytest.approx((2 + 9 + 5 + 2) / 4)
    assert summary["total_mae"] == pytest.approx((2 + 10 + 2 + 5) / 4)
    assert page._prediction_summary(frame.iloc[0:0]) == {"games": 0}


def _coverage(predicted: int, reasons: dict[str, int]) -> dict:
    excluded = sum(reasons.values())
    return {"scheduled_games": predicted + excluded, "predicted_games": predicted, "excluded_games": excluded, "excluded_by_reason": reasons}


def _coverage_captions(at: AppTest) -> list[str]:
    return [str(c.value) for c in at.caption if str(c.value).startswith("Showing ")]


def test_coverage_caption_says_how_much_of_the_schedule_is_shown(tmp_path, render):
    """Coverage is about Division I games only: an old card's non-D1 count is subtracted, never named."""
    reasons = {"not_d1_v_d1": 41, "start_time_tbd": 60, "invalid_tipoff": 2, "already_started": 1, "missing_neutral_site": 3, "weird_new_reason": 4, "another_new_one": 1}
    _publish_card(tmp_path, lines=False, coverage=_coverage(len(GAMES), reasons))
    captions = _coverage_captions(render())
    assert captions == [
        f"Showing 6 of {6 + 71} Division I games on the schedule. Not shown: 60 with no confirmed start time, "
        "5 with other data gaps, 3 with the game site not confirmed, 2 with a start time that could not be read, 1 already started when predictions were made."
    ]
    assert "—" not in captions[0] and "–" not in captions[0] and "not Division I vs" not in captions[0]


def test_coverage_caption_matches_the_producer_example(tmp_path, render):
    """The real 2026-11-02 card: 80 predicted of 119 Division I games, 39 with no confirmed start time."""
    games = [(f"Home {i}", f"Away {i}", 2.0, 140.0, None, 19.0, False) for i in range(1, 81)]
    _publish_card(tmp_path, lines=False, games=games, coverage=_coverage(80, {"start_time_tbd": 39}))
    assert _coverage_captions(render()) == ["Showing 80 of 119 Division I games on the schedule. Not shown: 39 with no confirmed start time."]


def test_coverage_caption_with_only_non_d1_left_out_shows_nothing(tmp_path, render):
    _publish_card(tmp_path, lines=False, coverage=_coverage(len(GAMES), {"not_d1_v_d1": 41}))
    assert not _coverage_captions(render())


def test_coverage_caption_sits_under_the_predictions_header(tmp_path, render):
    _publish_card(tmp_path, lines=False, coverage=_coverage(len(GAMES), {"start_time_tbd": 2}))
    at = render()
    tree = [str(getattr(e, "value", "")) for e in at.main]
    header_at = tree.index("Predictions for Monday, November 2")
    assert tree[header_at + 1] == "Showing 6 of 8 Division I games on the schedule. Not shown: 2 with no confirmed start time."


def test_coverage_caption_absent_or_zero_excluded_shows_nothing(tmp_path, render):
    _publish_card(tmp_path, lines=False)
    assert not _coverage_captions(render())
    _publish_card(tmp_path / "zero", lines=False, coverage=_coverage(len(GAMES), {}))
    assert not _coverage_captions(render(tmp_path / "zero"))


def test_coverage_caption_survives_long_school_names(tmp_path, render):
    games = [("Southern Illinois Edwardsville", "Miami (OH)", -2.5, 143.0, None, 19.0, False), ("Northern Illinois", "Texas A&M-Corpus Christi", 3.1, 145.5, None, 20.0, False)]
    _publish_card(tmp_path, lines=False, games=games, coverage=_coverage(2, {"start_time_tbd": 60, "not_d1_v_d1": 41}))
    at = render()
    assert _coverage_captions(at) == ["Showing 2 of 62 Division I games on the schedule. Not shown: 60 with no confirmed start time."]
    assert any(c.startswith("**Miami (OH) by 2.5**") for c in _game_cards(at))
    assert "Miami (OH) at Southern Illinois Edwardsville · 7:00 PM ET" in [str(c.value) for c in at.caption]


def test_intro_warns_that_early_season_predictions_are_less_certain(tmp_path, render):
    expected = "Early in the season the model leans on last season's results, so predictions are less certain until teams have played more games."
    assert expected in [str(i.value) for i in render(tmp_path / "nothing-published", today=None).info][0]
    _publish_card(tmp_path, lines=False)
    assert expected in [str(i.value) for i in render().info][0]


# ---- View menu: Top 25 and conferences -------------------------------------------------------------

CAPTION_PRESEASON = "Top 25: AP poll of Oct 20, 2026 (preseason). Conference order: WarrenNolan.com conference ranking, snapshot of Oct 24, 2026."
ALL_SIX_MENU = [
    "Top 25 (3 games)", "Big 12 (1 game)", "Big Ten (2 games)", "ACC (1 game)", "West Coast (1 game)",
    "Mid-American (1 game)", "Southland (1 game)", "Ohio Valley (1 game)",
]
# Games with no ranked team in them: Big Ten, Mid-American, Southland and Ohio Valley.
UNRANKED_GAMES = [GAMES[1], GAMES[3], GAMES[5]]
TEAMS.update({name: ("SEC", None) for name in (
    "Alabama", "Auburn", "Georgia", "LSU", "Ole Miss", "Vanderbilt", "Texas A&M", "Arkansas", "Tennessee", "Florida",
    "Mississippi State", "South Carolina",
)})
TEAMS.update({"Queens University": ("", None), "Merrimack": ("MAAC", None), "Wagner": ("NEC", None)})
# Three SEC games with a gap (3.0, 9.0, and 7.0 toward the away team), one more tied at 3.0 that tips earlier, two with no line.
SEC_GAMES = [
    ("Alabama", "Auburn", 5.0, 150.0, -2.0, 21.0, False),
    ("Georgia", "LSU", 10.0, 140.0, -1.0, 19.0, False),
    ("Ole Miss", "Vanderbilt", -2.0, 138.0, None, 15.0, False),
    ("Texas A&M", "Arkansas", 1.0, 147.0, None, 13.0, False),
    ("Tennessee", "Florida", -6.0, 142.0, -1.0, 18.0, False),
    ("Mississippi State", "South Carolina", 4.0, 139.0, -1.0, 20.0, False),
]


def test_view_menu_lists_top_25_then_conferences_in_file_order(tmp_path, render):
    _publish_card(tmp_path, lines=True)
    at = render()
    assert not at.error, [error.value for error in at.error]
    menu = at.selectbox(key="cbb_view")
    assert menu.label == "View" and list(menu.options) == ALL_SIX_MENU
    assert menu.value == "Top 25"
    # No "All games" view anywhere: every game is reached through Top 25 or a conference.
    assert not any(re.search(r"\ball\b", label.lower()) for label in menu.options) and len(at.expander) == 0
    assert _view_keys(at)[0] == "Top 25"
    # SWAC, Pac-12 and the other file entries with no game that day stay out of the menu.
    assert all(label.split(" (")[0] in {"Top 25", "Big 12", "Big Ten", "ACC", "West Coast", "Mid-American", "Southland", "Ohio Valley"} for label in menu.options)


def test_default_view_is_top_25_with_ranked_games_by_gap_and_the_poll_caption(tmp_path, render):
    _publish_card(tmp_path, lines=True)
    at = render()
    # Duke (#2) at Kansas, Michigan State (#14) and Wisconsin (#25), Gonzaga (#11) and Saint Mary's (#25): gaps 0.95, 11.00, 1.50.
    assert _headlines(at) == ["#14 Michigan State by 14.0", "#11 Gonzaga by 1.5", "Kansas by 4.2"]
    captions = [str(c.value) for c in at.caption]
    assert CAPTION_PRESEASON in captions
    assert "Games are listed by gap: how far the model's predicted margin is from the sportsbook line, largest first. Games with no line follow, by tip time." in captions
    # A later poll is not preseason; the date is the poll's own.
    _publish_card(tmp_path / "weekly", lines=True, top25=WEEKLY)
    assert "Top 25: AP poll of Nov 9, 2026. Conference order: WarrenNolan.com conference ranking, snapshot of Oct 24, 2026." in [str(c.value) for c in render(tmp_path / "weekly").caption]


def test_ranked_teams_get_a_number_prefix_and_ties_keep_both_numbers(tmp_path, render):
    _publish_card(tmp_path, lines=True)
    at = render()
    cards = _game_cards(at)
    assert any(card.startswith("**#14 Michigan State by 14.0**") for card in cards)
    assert any(card.startswith("**#11 Gonzaga by 1.5**") for card in cards)
    assert any(card.startswith("**Kansas by 4.2**") for card in cards), "an unranked winner has no prefix"
    captions = _game_captions(at)
    assert "#2 Duke at Kansas · 12:00 PM ET" in captions
    assert "#25 Wisconsin at #14 Michigan State · 4:00 PM ET" in captions
    assert "#25 Saint Mary's (CA) vs #11 Gonzaga · 7:00 PM ET · Neutral site" in captions
    # Two teams on #25 both keep it, and the games with an unranked team keep the plain name.
    assert sum("#25 " in caption for caption in captions) == 2
    assert "Oregon at UCLA · 2:00 PM ET" in _game_captions(render(view="Big Ten"))


def test_a_cross_conference_game_appears_in_both_conference_views_and_top_25(tmp_path, render):
    _publish_card(tmp_path, lines=True)
    duke_at_kansas = "#2 Duke at Kansas · 12:00 PM ET"
    for view in ("Top 25", "Big 12", "ACC"):
        assert duke_at_kansas in _game_captions(render(view=view)), view
    for view in ("Big Ten", "West Coast", "Mid-American", "Southland", "Ohio Valley"):
        assert duke_at_kansas not in _game_captions(render(view=view)), view
    assert _headlines(render(view="Big 12")) == _headlines(render(view="ACC")) == ["Kansas by 4.2"]
    assert _headlines(render(view="Big Ten")) == ["#14 Michigan State by 14.0", "UCLA by 12.0"]


def test_every_view_sorts_by_absolute_gap_then_games_with_no_line_by_tip_time(tmp_path, render):
    _publish_card(tmp_path, lines=True, games=SEC_GAMES)
    at = render()
    assert at.selectbox(key="cbb_view").value == "SEC"   # a poll exists but no ranked team plays, so the first conference
    # Georgia 9.0, Florida 7.0 (the gap points to the away team: absolute size counts), the 3.0 tie by tip time, then no line by tip time.
    assert _headlines(at) == ["Georgia by 10.0", "Florida by 6.0", "Mississippi State by 4.0", "Alabama by 5.0", "Texas A&M by 1.0", "Vanderbilt by 2.0"]
    assert _card_lines(at) == [
        "Line: Georgia -1 · Gap 9.00 toward Georgia", "Line: Tennessee -1 · Gap 7.00 toward Florida",
        "Line: Mississippi State -1 · Gap 3.00 toward Mississippi State", "Line: Alabama -2 · Gap 3.00 toward Alabama", "No line yet", "No line yet",
    ]
    # Switching views re-sorts with the same rule: the SEC view is unchanged and Top 25 has nothing in it.
    by_view = _across_views(at, _headlines)
    assert by_view["SEC"] == _headlines(at) and by_view["Top 25"] == []


def test_sorting_ties_fall_back_to_tip_time_then_home_team():
    import page_cbb_daily as page

    games = pd.DataFrame({
        "home_team": ["Zeta", "Alpha", "Mid", "Early", "Gamma", "Beta"],
        "_has_line": [True, True, True, False, False, False],
        "_gap": [3.0, 3.0, 5.0, None, None, None],
        "_tip": pd.to_datetime(["2026-11-02T20:00:00Z"] * 2 + ["2026-11-02T23:00:00Z"] + ["2026-11-02T17:00:00Z", "2026-11-02T22:00:00Z", "2026-11-02T22:00:00Z"], utc=True),
    })
    assert page._sorted_for_display(games)["home_team"].tolist() == ["Mid", "Alpha", "Zeta", "Early", "Beta", "Gamma"]


def test_default_view_is_the_first_conference_when_there_is_no_poll(tmp_path, render):
    _publish_card(tmp_path, lines=True, games=UNRANKED_GAMES, top25=None)
    at = render()
    assert not at.error, [error.value for error in at.error]
    assert list(at.selectbox(key="cbb_view").options) == ["Top 25 (0 games)", "Big Ten (1 game)", "Mid-American (1 game)", "Southland (1 game)", "Ohio Valley (1 game)"]
    assert at.selectbox(key="cbb_view").value == "Big Ten"
    assert _headlines(at) == ["UCLA by 12.0"]
    assert "Top 25: no AP poll is available for this date. Conference order: WarrenNolan.com conference ranking, snapshot of Oct 24, 2026." in [str(c.value) for c in at.caption]
    at = render(view="Top 25")
    assert not _game_cards(at)
    assert "The AP Top 25 poll is not available for this date, so there are no ranked teams to show." in [str(i.value) for i in at.info]


def test_default_view_is_the_first_conference_when_no_ranked_team_plays(tmp_path, render):
    _publish_card(tmp_path, lines=True, games=UNRANKED_GAMES, top25=WEEKLY)
    at = render()
    assert at.selectbox(key="cbb_view").value == "Big Ten" and _view_menu(at)[0] == "Top 25 (0 games)"
    assert "Top 25: AP poll of Nov 9, 2026. Conference order: WarrenNolan.com conference ranking, snapshot of Oct 24, 2026." in [str(c.value) for c in at.caption]
    at = render(view="Top 25")
    assert not _game_cards(at) and "No ranked team plays on this date." in [str(i.value) for i in at.info]


def test_blank_and_unknown_conferences_go_last_under_other(tmp_path, render):
    games = [("Queens University", "Kansas", 2.0, 141.0, -1.0, 19.0, False), ("Merrimack", "Wagner", -1.0, 128.0, None, 18.0, False)]
    _publish_card(tmp_path, lines=True, games=games)
    at = render()
    # A blank conference and one the order file does not list (MAAC) are both "Other"; the game with Kansas is also in Big 12.
    assert list(at.selectbox(key="cbb_view").options) == ["Top 25 (0 games)", "Big 12 (1 game)", "NEC (1 game)", "Other (2 games)"]
    assert at.selectbox(key="cbb_view").value == "Big 12"
    assert _headlines(render(view="Other")) == ["Queens University by 2.0", "Wagner by 1.0"]
    assert _headlines(render(view="Big 12")) == ["Queens University by 2.0"] and _headlines(render(view="NEC")) == ["Wagner by 1.0"]


def test_a_card_without_the_optional_columns_still_renders(tmp_path, render):
    """Cards written before the conference and rank columns existed load and show every game under Other."""
    _publish_card(tmp_path, lines=True, extras=False)
    at = render()
    assert not at.error and not at.exception
    assert list(at.selectbox(key="cbb_view").options) == ["Top 25 (0 games)", "Other (6 games)"]
    assert at.selectbox(key="cbb_view").value == "Other" and len(_game_cards(at)) == 6
    assert not any(headline.startswith("#") for headline in _headlines(at))


def test_conference_order_file_failure_falls_back_to_alphabetical_with_a_note(tmp_path, render, monkeypatch):
    import cbb_daily_data

    _publish_card(tmp_path, lines=True)
    monkeypatch.setattr(cbb_daily_data, "CONFERENCE_ORDER_PATH", tmp_path / "missing.json")
    at = render()
    assert not at.error and not at.exception
    assert list(at.selectbox(key="cbb_view").options) == [
        "Top 25 (3 games)", "ACC (1 game)", "Big 12 (1 game)", "Big Ten (2 games)", "MAC (1 game)", "OVC (1 game)", "Southland (1 game)", "WCC (1 game)",
    ]
    captions = [str(c.value) for c in at.caption]
    assert "Top 25: AP poll of Oct 20, 2026 (preseason). Conference order: alphabetical, because the conference ranking list could not be loaded." in captions
    assert not any("WarrenNolan" in caption for caption in captions)


def test_view_and_search_do_not_go_stale_when_the_card_date_changes(tmp_path, render):
    _publish_card(tmp_path, lines=True)
    next_day = date(2026, 11, 3)
    _publish_card(tmp_path, lines=True, games=UNRANKED_GAMES[:2], day=next_day, top25=None)
    at = render()
    day_picker = at.selectbox(key="cbb_card_date")
    assert day_picker.value == DAY.isoformat()

    # A conference the next day also has survives the date change; one it lacks resets to that day's default.
    at.selectbox(key="cbb_view").set_value("Big Ten").run()
    at.selectbox(key="cbb_card_date").set_value(next_day.isoformat()).run()
    assert not at.exception and at.selectbox(key="cbb_view").value == "Big Ten"
    at.selectbox(key="cbb_card_date").set_value(DAY.isoformat()).run()
    at.selectbox(key="cbb_view").set_value("Ohio Valley").run()
    at.selectbox(key="cbb_card_date").set_value(next_day.isoformat()).run()
    assert not at.exception and at.selectbox(key="cbb_view").value == "Big Ten"
    assert list(at.selectbox(key="cbb_view").options)[0] == "Top 25 (0 games)"

    # Top 25 is the default, not a choice to carry onto a day with no ranked team.
    at.selectbox(key="cbb_card_date").set_value(DAY.isoformat()).run()
    at.selectbox(key="cbb_view").set_value("Top 25").run()
    at.selectbox(key="cbb_card_date").set_value(next_day.isoformat()).run()
    assert at.selectbox(key="cbb_view").value == "Big Ten" and _game_cards(at)

    # A search is dropped when the date changes, so it never hides the new day's games.
    at.selectbox(key="cbb_card_date").set_value(DAY.isoformat()).run()
    at.text_input(key="cbb_team_search").set_value("duke").run()
    assert _headlines(at) == ["Kansas by 4.2"]
    at.selectbox(key="cbb_card_date").set_value(next_day.isoformat()).run()
    assert at.text_input(key="cbb_team_search").value == "" and not at.selectbox(key="cbb_view").disabled
    assert _game_cards(at) and not [i for i in at.info if "No games match" in str(i.value)]


def test_there_is_no_all_games_list_and_the_ats_section_keeps_plays_record_and_benchmark(tmp_path, render):
    entry = _publish_card(tmp_path, lines=True)
    _publish_results(tmp_path, entry, {1: (80, 70), 2: (70, 66), 3: (80, 70), 4: (70, 71), 5: (70, 68), 6: None})
    at = render(select=DAY.isoformat())
    text = _all_text(at)
    assert len(at.expander) == 0 and "All games on this card" not in text
    assert sorted(_pick_cards(at)) == ["**Shadow pick: Michigan State -3**", "**Shadow pick: Ohio +0.25**"]
    assert "2 wins · 0 losses · 0 pushes · ATS rate 100.0%" in text
    assert "Historical benchmark context" in [str(s.value) for s in at.subheader]
    assert not re.search(r"\bedge\b", text, flags=re.IGNORECASE), "the page says gap, never edge"
    assert "Model gap is the model's predicted margin minus the margin the spread implies" in text
    assert "result: win" in text


def test_the_8_5_badge_marks_only_the_plays(tmp_path, render):
    _publish_card(tmp_path, lines=True)
    at = render()
    by_view = _across_views(at, _badges)
    # Michigan State (+11.00) is a play and so is Ohio (-9.65); UCLA (+8.46) is not.
    assert by_view["Top 25"] == [BADGE] and by_view["Big Ten"] == [BADGE] and by_view["Mid-American"] == [BADGE]
    assert by_view["ACC"] == by_view["West Coast"] == by_view["Big 12"] == by_view["Southland"] == by_view["Ohio Valley"] == []
    assert len(_game_cards(render(view="Big Ten"))) == 2, "the unmarked UCLA game sits beside the marked one"


def test_line_row_names_the_team_the_line_favors_and_the_side_of_the_gap():
    import page_cbb_daily as page

    def line(spread, edge, *, has_line=True):
        row = pd.Series({"_has_line": has_line, "market_home_spread": spread, "model_edge": edge})
        game = {"home": "Kentucky", "away": "Louisville"}
        return page._line_row(row, game, 8.5)

    assert line(-5.5, 1.9) == "Line: Kentucky -5.5 · Gap 1.90 toward Kentucky"        # home favored, model leans home
    assert line(3.0, -1.25) == "Line: Louisville -3 · Gap 1.25 toward Louisville"      # away favored, model leans away
    assert line(-5.5, -0.4) == "Line: Kentucky -5.5 · Gap 0.40 toward Louisville"      # the model leans the other way
    assert line(3.25, 0.75) == "Line: Louisville -3.25 · Gap 0.75 toward Kentucky"
    assert line(0.0, 2.0) == "Line: pick'em · Gap 2.00 toward Kentucky" and line(-0.0, -2.0) == "Line: pick'em · Gap 2.00 toward Louisville"
    assert line(-1.0, 0.001) == "Line: Kentucky -1 · Gap 0.00"
    assert line(-1.0, 8.496) == "Line: Kentucky -1 · Gap 8.49 toward Kentucky" and line(-1.0, -8.5) == "Line: Kentucky -1 · Gap 8.50 toward Louisville"
    assert line("", "", has_line=False) == "No line yet"
    assert line(-5.5, 1.9, has_line=False) == "No line yet"
