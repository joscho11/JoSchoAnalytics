import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
SITE_PAGES = ROOT / "site_pages"
FIXTURES = ROOT / "tests" / "fixtures" / "optimizer"
SALARY_FIXTURE = FIXTURES / "dk_salaries.csv"
PROJECTION_FIXTURE = FIXTURES / "direct_dk_projections.csv"
sys.path[:0] = [str(ROOT), str(SITE_PAGES)]

import dfs_runtime as runtime  # noqa: E402
from scripts.sync_optimizer_projection import _canonical_csv_bytes  # noqa: E402
from dashboard_chrome import exact_table_height  # noqa: E402


def _render_page():
    __import__("page_dfs").render()


def _run():
    at = AppTest.from_function(_render_page, default_timeout=120).run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    return at


def _upload_inputs(at, *, include_projection=True):
    at.file_uploader(key="dfs_salary_upload").set_value(
        ("DKSalaries.csv", SALARY_FIXTURE.read_bytes(), "text/csv")
    )
    if include_projection:
        at.file_uploader(key="dfs_projection_upload").set_value(
            ("projections_2026_week01.csv", PROJECTION_FIXTURE.read_bytes(), "text/csv")
        )
    at = at.run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    return at


def test_runtime_and_test_fixtures_solve():
    assert SALARY_FIXTURE.is_file() and PROJECTION_FIXTURE.is_file()
    pipeline = runtime.load_pipeline()
    pool, lineup, summary = pipeline.solve(SALARY_FIXTURE, PROJECTION_FIXTURE)
    assert summary["n_rows"] == 26 and summary["n_games"] == 2
    assert int(pool["optimization_eligible"].sum()) == 24
    assert lineup is not None and len(lineup) == 9
    assert int(lineup["salary"].sum()) <= 50_000
    assert exact_table_height(len(lineup)) == 353


def test_page_is_real_slate_upload_only():
    at = _run()
    # Only the History/Optimizer View control exists before a salary upload;
    # the Cash/Tournament objective control only appears once a slate is in.
    assert {widget.key for widget in at.segmented_control} == {"dfs_view"}
    view = next(widget for widget in at.segmented_control if widget.key == "dfs_view")
    assert view.value == "Optimizer"
    assert {widget.label for widget in at.file_uploader} == {
        "DraftKings salary CSV",
        "Direct-DK projection CSV",
    }
    assert any("Upload a DraftKings NFL Classic salary CSV" in item.value for item in at.info)
    assert any(
        exp.label == "What this beta does — and does not do" for exp in at.expander
    )


def test_valid_salary_explains_missing_projection(tmp_path, monkeypatch):
    monkeypatch.setenv("DFS_OPTIMIZER_ROOT", str(tmp_path / "optimizer"))
    monkeypatch.setenv("DFS_PROJECTION_ROOT", str(tmp_path / "published"))
    monkeypatch.setattr(runtime, "active_fantasy_source", lambda root=None: (
        {"build_id": "fantasy-2026w03-test", "season": 2026, "week": 3, "sha256": "a" * 64},
        tmp_path / "fantasy.csv",
    ))
    at = _upload_inputs(_run(), include_projection=False)
    assert any("Salary slate accepted" in item.value for item in at.success)
    assert any("2026 Week 3 DFS projections are not published yet" in item.value for item in at.warning)
    assert not any(button.label == "Optimize lineup" for button in at.button)


def test_uploaded_inputs_optimize_and_expose_dk_download():
    at = _upload_inputs(_run())
    assert any(button.label == "Optimize lineup" for button in at.button)
    next(button for button in at.button if button.label == "Optimize lineup").click()
    at = at.run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    assert any(sub.value == "Optimized lineup" for sub in at.subheader)
    downloads = at.get("download_button")
    assert any(button.label == "Download DraftKings lineup" for button in downloads)
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Salary used"] == "$50,000"
    assert metrics["Projected DK points"] == "152.5"


def test_tournament_mode_without_ceiling_falls_back_cleanly():
    at = _upload_inputs(_run())
    objective = next(widget for widget in at.segmented_control if widget.key == "dfs_objective")
    assert objective.options == ["Cash (expected points)", "Tournament (ceiling)"]
    assert objective.value == "Tournament (ceiling)"
    assert any("no `ceiling_pts` column" in item.value for item in at.warning)
    assert any(button.label == "Optimize lineup" for button in at.button)


def test_cash_mode_is_available_and_selectable():
    at = _upload_inputs(_run())
    objective = next(widget for widget in at.segmented_control if widget.key == "dfs_objective")
    assert objective.value == "Tournament (ceiling)"
    at = objective.set_value("Cash (expected points)").run()
    assert not at.exception, at.exception
    assert not any("no `ceiling_pts` column" in item.value for item in at.warning)


def test_failed_resolve_clears_the_previous_download():
    at = _upload_inputs(_run())
    next(button for button in at.button if button.label == "Optimize lineup").click()
    at = at.run()
    assert at.get("download_button")

    locks = next(widget for widget in at.multiselect if widget.key == "dfs_locked")
    locks.set_value(["9001", "9002"])
    next(button for button in at.button if button.label == "Optimize lineup").click()
    at = at.run()
    assert any("No legal lineup" in item.value for item in at.error)
    assert not at.get("download_button")
    assert not any(sub.value == "Optimized lineup" for sub in at.subheader)


def test_stale_team_mismatch_excluded_by_default():
    salary = SALARY_FIXTURE.read_text(encoding="utf-8")
    projection = PROJECTION_FIXTURE.read_text(encoding="utf-8")
    # Re-team one projected player relative to the salary slate: same name,
    # wrong team. matching.py resolves this as a name-unique "team_mismatch",
    # not a hard non-match, so it stays eligible unless the page excludes it.
    stale_projection = projection.replace(
        "demo-qb-a,Demo QB Alpha,QB,BUF,KC,2026,1,24.8,direct_dk_points",
        "demo-qb-a,Demo QB Alpha,QB,DAL,NYG,2026,1,24.8,direct_dk_points",
    )
    assert stale_projection != projection

    at = _run()
    at.file_uploader(key="dfs_salary_upload").set_value(("DKSalaries.csv", salary.encode("utf-8"), "text/csv"))
    at.file_uploader(key="dfs_projection_upload").set_value(
        ("projections_2026_week01.csv", stale_projection.encode("utf-8"), "text/csv")
    )
    at = at.run()
    assert not at.exception, at.exception

    checkbox = next(w for w in at.checkbox if w.key == "dfs_exclude_stale_team")
    assert checkbox.value is True
    assert "matched on name only" in checkbox.label
    locked = next(w for w in at.multiselect if w.key == "dfs_locked")
    n_options_excluded = len(locked.options)

    at = checkbox.set_value(False).run()
    assert not at.exception, at.exception
    locked_after = next(w for w in at.multiselect if w.key == "dfs_locked")
    assert len(locked_after.options) == n_options_excluded + 1


def _write_published_projection(
    root, *, week, build_id, source_sha, games,
    revision="1" * 40, synced_at="2026-09-27T12:00:00+00:00",
):
    projection = root / f"projections_2026_week{week:02d}.csv"
    projection.parent.mkdir(parents=True, exist_ok=True)
    projection.write_bytes(PROJECTION_FIXTURE.read_bytes())
    metadata = {
        "product": "dfs_optimizer_v1",
        "scoring": "draftkings_classic",
        "projection_units": "direct_dk_points",
        "season": 2026,
        "week": week,
        "source_build_id": build_id,
        "source_artifact_sha256": source_sha,
        "producer_revision": revision,
        "synced_at_utc": synced_at,
        "games": games,
        "projection_csv_sha256": runtime.file_sha256(projection),
    }
    projection.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
    return projection


def test_active_projection_is_bound_to_release_and_salary_slate(tmp_path, monkeypatch):
    published = tmp_path / "published"
    published.mkdir()
    monkeypatch.setattr(runtime, "published_projection_root", lambda: published)
    source_sha = "a" * 64
    games = [{"date": "2026-09-13", "teams": ["BUF", "KC"]}]
    _write_published_projection(
        published, week=2, build_id="fantasy-2026w02-old", source_sha="b" * 64, games=games
    )
    older_projection = _write_published_projection(
        published / "2026" / "week03" / "fantasy-2026w03-current" / ("f" * 12),
        week=3, build_id="fantasy-2026w03-current", source_sha=source_sha, games=games,
        revision="f" * 40, synced_at="2026-09-26T12:00:00+00:00",
    )
    projection = _write_published_projection(
        published / "2026" / "week03" / "fantasy-2026w03-current" / ("1" * 12),
        week=3, build_id="fantasy-2026w03-current", source_sha=source_sha, games=games,
    )
    build = {
        "build_id": "fantasy-2026w03-current",
        "sha256": source_sha,
        "season": 2026,
        "week": 3,
    }
    assert runtime.active_projection_path(build) == projection

    salary = pd.DataFrame([{"away": "BUF", "home": "KC", "slate_date": "09/13/2026"}])
    assert runtime.projection_matches_slate(projection, salary, runtime.load_pipeline().norm_team)
    mismatched_date = salary.assign(slate_date="09/20/2026")
    assert not runtime.projection_matches_slate(
        projection, mismatched_date, runtime.load_pipeline().norm_team
    )

    corrected = {**build, "build_id": "fantasy-2026w03-corrected", "sha256": "c" * 64}
    assert runtime.active_projection_path(corrected) is None

    projection.write_text("tampered\n", encoding="utf-8")
    assert runtime.active_projection_path(build) == older_projection


def test_sync_csv_checksum_bytes_are_line_ending_stable():
    import hashlib

    windows_csv = b"player,team\r\nname,SF\r\n"
    linux_csv = b"player,team\nname,SF\n"
    canonical_windows = _canonical_csv_bytes(windows_csv)
    canonical_linux = _canonical_csv_bytes(linux_csv)
    assert canonical_windows == canonical_linux == linux_csv
    assert hashlib.sha256(canonical_windows).digest() == hashlib.sha256(linux_csv).digest()


def test_mismatched_override_still_fails_matchup_validation():
    salary = SALARY_FIXTURE.read_text(encoding="utf-8")
    projection = PROJECTION_FIXTURE.read_text(encoding="utf-8").replace(
        "demo-qb-a,Demo QB Alpha,QB,BUF,KC,2026,1,24.8,direct_dk_points",
        "demo-qb-a,Demo QB Alpha,QB,BUF,ZZZ,2026,1,24.8,direct_dk_points",
    )
    assert projection != PROJECTION_FIXTURE.read_text(encoding="utf-8")

    at = _run()
    at.file_uploader(key="dfs_salary_upload").set_value(
        ("DKSalaries.csv", salary.encode("utf-8"), "text/csv")
    )
    at.file_uploader(key="dfs_projection_upload").set_value(
        ("stale-projections.csv", projection.encode("utf-8"), "text/csv")
    )
    at = at.run()
    assert not at.exception, at.exception
    assert any("Slate validation failed" in item.value for item in at.error)


# ------------------------------------------------------------- History view
HISTORY_FIXTURES = ROOT / "tests" / "fixtures" / "optimizer_history"


def _all_rendered_text(at) -> str:
    """Every user-visible string AppTest exposes: markdown, captions, metrics,
    subheaders, info banners, and every rendered dataframe's own cell text
    (both the desktop and phone copies dataframe_phone_desktop draws)."""
    parts = []
    for md in at.markdown:
        parts.append(str(md.value))
    for cap in at.caption:
        parts.append(str(cap.value))
    for metric in at.metric:
        parts.append(f"{metric.label} {metric.value} {metric.delta or ''}")
    for sub in at.subheader:
        parts.append(str(sub.value))
    for info in at.info:
        parts.append(str(info.value))
    for df_el in at.dataframe:
        parts.append(df_el.value.to_csv(index=False))
    return "\n".join(parts)


def _switch_to_history(at):
    view = next(widget for widget in at.segmented_control if widget.key == "dfs_view")
    at = view.set_value("History").run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    return at


def _render_history_only():
    __import__("page_dfs")._render_history()


def _history_at(monkeypatch, root=HISTORY_FIXTURES):
    monkeypatch.setattr(runtime, "history_root", lambda: root)
    at = AppTest.from_function(_render_history_only, default_timeout=120).run()
    assert not at.exception, at.exception
    assert not at.error, [item.value for item in at.error]
    return at


def _metrics(at) -> dict:
    return {(metric.label, metric.value) for metric in at.metric}


def test_history_defaults_to_latest_season_and_week_and_shows_only_that_week(monkeypatch):
    at = _history_at(monkeypatch)
    season = at.selectbox(key="dfs_history_season")
    assert season.options == ["2026", "2025"] and season.value == 2026
    week = at.selectbox(key="dfs_history_week_2026")
    assert week.options == ["Week 2", "Week 3"] and week.value == 3

    # Week 3 has two lineups: the untouched one and the one with exclusions.
    assert _metrics(at) == {
        ("Actual DK points", "150.9"), ("Finish", "Top 17%"),
        ("Actual DK points", "162.5"), ("Finish", "Top 9%"),
    }
    assert any("With 2 exclusions made before lock" in md.value for md in at.markdown)
    # Two lineups, each drawn as a desktop and a phone copy.
    assert len(at.dataframe) == 4
    # Nothing from Week 2 or from another season is on screen.
    assert not any("122.1" in metric.value for metric in at.metric)
    assert not any("98.5" in metric.value for metric in at.metric)


def test_history_tables_end_in_a_total_row_not_a_caption(monkeypatch):
    at = _history_at(monkeypatch)
    desktop, phone = at.dataframe[0].value, at.dataframe[1].value
    assert list(desktop.columns) == [
        "Slot", "Player", "Pos", "Team", "Salary", "Ceiling", "Mean", "Actual", "Own",
    ]
    assert list(phone.columns) == ["Slot", "Player", "Salary", "Actual"]
    assert len(desktop) == len(phone) == 10  # nine players plus the Total row

    total = desktop.iloc[-1]
    assert total["Slot"] == "Total"
    assert total["Salary"] == 50_000
    assert total["Actual"] == pytest.approx(150.88)
    assert total["Ceiling"] == pytest.approx(175.6)
    assert total["Mean"] == pytest.approx(131.75)
    assert phone.iloc[-1]["Slot"] == "Total"
    assert phone.iloc[-1]["Actual"] == pytest.approx(150.88)
    # The totals used to live in a small caption under the table.
    assert not any(cap.value.startswith("Total:") for cap in at.caption)


def test_history_week_dropdown_switches_to_one_other_week(monkeypatch):
    at = _history_at(monkeypatch)
    at = at.selectbox(key="dfs_history_week_2026").set_value(2).run()
    assert not at.exception, at.exception
    assert _metrics(at) == {("Actual DK points", "122.1"), ("Finish", "Top 36%")}
    assert len(at.dataframe) == 2  # one lineup: desktop and phone copies
    assert not any("With 2 exclusions" in md.value for md in at.markdown)
    assert any("Field median 100 pts" in cap.value for cap in at.caption)


def test_history_season_dropdown_switches_season_and_weeks(monkeypatch):
    at = _history_at(monkeypatch)
    at = at.selectbox(key="dfs_history_season").set_value(2025).run()
    assert not at.exception, at.exception
    week = at.selectbox(key="dfs_history_week_2025")
    assert week.options == ["Week 1"] and week.value == 1
    assert _metrics(at) == {("Actual DK points", "98.5"), ("Finish", "Top 61%")}


def test_history_every_season_and_week_is_free_of_forbidden_text(monkeypatch):
    at = _history_at(monkeypatch)
    for season, weeks in ((2026, (2, 3)), (2025, (1,))):
        at = at.selectbox(key="dfs_history_season").set_value(season).run()
        for week in weeks:
            at = at.selectbox(key=f"dfs_history_week_{season}").set_value(week).run()
            assert not at.exception, at.exception
            # Scoped to the History section: the page header mentions Cash mode
            # and the salary cap, which are not leakage.
            text = _all_rendered_text(at).casefold()
            for forbidden in ("cash", "$", "contest", "joscho"):
                assert forbidden not in text, f"{forbidden!r} in {season} week {week}"


def test_history_view_through_the_page_uses_the_same_dropdowns(monkeypatch):
    monkeypatch.setattr(runtime, "history_root", lambda: HISTORY_FIXTURES)
    at = _switch_to_history(_run())
    assert any(sub.value == "History" for sub in at.subheader)
    assert at.selectbox(key="dfs_history_season").value == 2026
    assert at.selectbox(key="dfs_history_week_2026").value == 3


def test_history_view_missing_artifacts_shows_info_not_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "history_root", lambda: tmp_path / "no_such_history")
    at = _switch_to_history(_run())
    assert any("No published History weeks yet" in item.value for item in at.info)


def test_default_view_is_optimizer_and_history_does_not_disturb_it(monkeypatch):
    monkeypatch.setattr(runtime, "history_root", lambda: HISTORY_FIXTURES)
    at = _run()
    view = next(widget for widget in at.segmented_control if widget.key == "dfs_view")
    assert view.value == "Optimizer"
    assert any("Upload a DraftKings NFL Classic salary CSV" in item.value for item in at.info)

    at = _switch_to_history(at)
    assert any(sub.value == "History" for sub in at.subheader)

    # Switching back to Optimizer restores the ordinary upload-only state.
    view = next(widget for widget in at.segmented_control if widget.key == "dfs_view")
    at = view.set_value("Optimizer").run()
    assert not at.exception, at.exception
    assert any("Upload a DraftKings NFL Classic salary CSV" in item.value for item in at.info)
    assert not any(sub.value == "History" for sub in at.subheader)
    assert not at.selectbox
