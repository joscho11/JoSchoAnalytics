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
    row = {column: "" for column in CARD_COLUMNS}
    row.update({
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


def _publish_card(root: Path, *, lines: bool, games=GAMES, day: date = DAY, status: str | None = None, name: str = "card.csv", coverage: dict | None = None) -> dict:
    rows = [_row(i + 1, game, lines=lines, day=day) for i, game in enumerate(games)]
    if status is None:
        status = "official" if any(r["market_status"] == "available" for r in rows) else "unavailable"
    root.mkdir(parents=True, exist_ok=True)
    artifact = root / f"{day.isoformat()}-{name}"
    pd.DataFrame(rows, columns=CARD_COLUMNS).to_csv(artifact, index=False, lineterminator="\n")
    metadata = {
        "schema_version": CARD_SCHEMA_VERSION, "product": "cbb_daily_spreads", "season": 2027, "game_date_et": day.isoformat(),
        "status": "published" if rows else "no_games_scheduled", "artifact_sha256": sha256_file(artifact), "expected_rows": len(rows),
        "expected_game_ids": [r["game_id"] for r in rows], "historical_benchmark_hash": BENCHMARK_HASH, "threshold": 8.5,
        "prediction_run_hash": "pred", "line_snapshot_status": status, "prediction_at_utc": _utc(8.3333, day),
        "attribution": "Data provided by CollegeBasketballData.com", **HASHES,
    }
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
    loaders = (cbb_daily_data.load_manifest, cbb_daily_data.load_card, cbb_daily_data.load_results)
    harness = tmp_path / "harness.py"
    harness.write_text(
        f"import sys; sys.path[:0]=[r'{ROOT}', r'{ROOT / 'site_pages'}']\n"
        "import page_cbb_daily; page_cbb_daily.render()\n",
        encoding="utf-8",
    )

    def _render(root: Path | None = None, *, today: date | None = DAY, select: str | None = None, search: str | None = None) -> AppTest:
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


def _list_lines(at: AppTest) -> list[str]:
    assert len(at.expander) == 1, "the all-games list is one expander"
    return str(at.expander[0].markdown[0].value).splitlines()


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
    # 1) Predictions-only card: no picks, a visible notice, no HOME/AWAY labels anywhere.
    only = tmp_path / "only"
    _publish_card(only, lines=False)
    at = render(only)
    text = _all_text(at)
    assert not at.error, [error.value for error in at.error]
    cards = _game_cards(at)
    assert "**Kansas by 4.2** · 68% win probability" in cards
    assert "**Miami (OH) by 9.4**" not in " ".join(cards)
    assert any(card.startswith("**Ohio by 9.4** · 84% win probability") for card in cards)
    assert any(card.startswith("**Texas A&M-Corpus Christi by 6.3**") for card in cards)
    for name in ("Kansas", "Duke", "UCLA", "Oregon", "Michigan State", "Wisconsin", "Gonzaga", "Saint Mary's (CA)"):
        assert name in text
    assert NOTICE in [str(info.value) for info in at.info]
    assert not _pick_cards(at) and len(at.expander) == 0
    assert "Shadow pick" not in text
    assert not re.search(r"\b(HOME|AWAY)\b", text)

    # 2) Card with lines: exact spreads, two-decimal edges, an 8.46 edge is not a play, picks are team names.
    lined = tmp_path / "lined"
    _publish_card(lined, lines=True)
    at = render(lined)
    text = _all_text(at)
    assert not at.error, [error.value for error in at.error]
    assert NOTICE not in text
    lines = _list_lines(at)
    kansas = next(line for line in lines if line.startswith("- Duke at Kansas"))
    assert "Kansas -3.25" in kansas and "model edge +0.95" in kansas and kansas.endswith("No play")
    ucla = next(line for line in lines if line.startswith("- Oregon at UCLA"))
    assert "UCLA -3.5" in ucla and "model edge +8.46" in ucla and ucla.endswith("No play") and "Shadow pick" not in ucla
    assert any("Gonzaga PK" in line for line in lines)
    assert any(line.startswith("- Texas A&M-Corpus Christi at Southeast Missouri State") and line.endswith("No line") for line in lines)
    assert sorted(_pick_cards(at)) == ["**Shadow pick: Michigan State -3**", "**Shadow pick: Ohio +0.25**"]
    assert "UCLA" not in " ".join(_pick_cards(at))
    assert "+8.50" not in text
    assert not re.search(r"\b(HOME|AWAY)\b", text)
    assert "ATS plays are shown" not in text


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
    assert "Duke at Kansas · 12:00 PM ET" in captions
    assert "Saint Mary's (CA) vs Gonzaga · 7:00 PM ET · Neutral site" in captions
    assert all("Neutral site" not in caption for caption in captions if "Kansas" in caption)


def test_team_search_filters_the_cards_and_the_list(tmp_path, render):
    _publish_card(tmp_path, lines=True)
    at = render(search="duke")
    assert len(_game_cards(at)) == 1 and _game_cards(at)[0].startswith("**Kansas by 4.2**")
    lines = _list_lines(at)
    assert len(lines) == 1 and "Duke" in lines[0]
    at = render(search="no such team")
    assert [str(info.value) for info in at.info if "No games match" in str(info.value)] == ["No games match that search."]
    assert not _game_cards(at)


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
    # Per-game results on the cards.
    finals = [str(m.value) for m in at.markdown if str(m.value).startswith("Final:")]
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
    outcomes = [str(c.value) for c in at.caption if "model edge" in str(c.value) and "result:" in str(c.value)]
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
    entry_text = _all_text(render())
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
    reasons = {"not_d1_v_d1": 41, "start_time_tbd": 60, "invalid_tipoff": 2, "already_started": 1, "missing_neutral_site": 3, "weird_new_reason": 4, "another_new_one": 1}
    _publish_card(tmp_path, lines=False, coverage=_coverage(len(GAMES), reasons))
    captions = _coverage_captions(render())
    assert captions == [
        f"Showing 6 of {6 + 112} games on the schedule. Not shown: 60 with no confirmed start time, 41 not Division I vs Division I, "
        "5 with other data gaps, 3 with the game site not confirmed, 2 with a start time that could not be read, 1 already started when predictions were made."
    ]
    assert "—" not in captions[0] and "–" not in captions[0]


def test_coverage_caption_sits_under_the_predictions_header(tmp_path, render):
    _publish_card(tmp_path, lines=False, coverage=_coverage(len(GAMES), {"start_time_tbd": 2}))
    at = render()
    tree = [str(getattr(e, "value", "")) for e in at.main]
    header_at = tree.index("Predictions for Monday, November 2")
    assert tree[header_at + 1] == f"Showing 6 of 8 games on the schedule. Not shown: 2 with no confirmed start time."


def test_coverage_caption_absent_or_zero_excluded_shows_nothing(tmp_path, render):
    _publish_card(tmp_path, lines=False)
    assert not _coverage_captions(render())
    _publish_card(tmp_path / "zero", lines=False, coverage=_coverage(len(GAMES), {}))
    assert not _coverage_captions(render(tmp_path / "zero"))


def test_coverage_caption_survives_long_school_names(tmp_path, render):
    games = [("Southern Illinois Edwardsville", "Miami (OH)", -2.5, 143.0, None, 19.0, False), ("Northern Illinois", "Texas A&M-Corpus Christi", 3.1, 145.5, None, 20.0, False)]
    _publish_card(tmp_path, lines=False, games=games, coverage=_coverage(2, {"start_time_tbd": 60, "not_d1_v_d1": 41}))
    at = render()
    assert _coverage_captions(at) == ["Showing 2 of 103 games on the schedule. Not shown: 60 with no confirmed start time, 41 not Division I vs Division I."]
    assert any(c.startswith("**Miami (OH) by 2.5**") for c in _game_cards(at))
    assert "Miami (OH) at Southern Illinois Edwardsville · 7:00 PM ET" in [str(c.value) for c in at.caption]


def test_intro_warns_that_early_season_predictions_are_less_certain(tmp_path, render):
    expected = "Early in the season the model leans on last season's results, so predictions are less certain until teams have played more games."
    assert expected in [str(i.value) for i in render(tmp_path / "nothing-published", today=None).info][0]
    _publish_card(tmp_path, lines=False)
    assert expected in [str(i.value) for i in render().info][0]
